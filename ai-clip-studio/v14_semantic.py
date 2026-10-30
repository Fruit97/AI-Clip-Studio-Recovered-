"""V14: topic-agnostic visual grounding of narration to observed uploaded video.

Gemini scores every proposed match against real video timestamps. The pipeline
will omit ungrounded narration instead of silently substituting related-looking
footage. No topic/keyword allowlist: people, objects, actions and events are
matched with the same generic visual-evidence protocol.

A score is a model estimate, NOT a guarantee of ground truth. Source footage
cannot show events that are not actually present in the upload.
"""
from __future__ import annotations
import json
import re

VERSION = 'v14-universal-visual-grounding-2026-10-30'
MIN_CONFIDENCE = .78


def make_prompt(timecodes, length, tone):
    return (
        'You are an expert Thai-language documentary picture editor reviewing the UPLOADED VIDEO. '
        'Respond as JSON only. Do not invent footage or visual claims. '
        'First inspect the actual moving footage at the candidate timestamps and list observed subjects, '
        'what each subject is doing, setting and visual changes. '
        'Choose narration based on scenes that really exist, not scenes you would like to exist. '
        'For EVERY individual narration beat, the selected on-screen footage must MEAN the same thing '
        'as the whole spoken beat — including who/what, action, attributes, location and the event. '
        'This is a UNIVERSAL rule for absolutely any topic. Never match merely because one word or '
        'background object is shared. A scene showing a similar category but a different action is '
        'NOT a match. Inferences or unseen events must not be claimed as directly shown. '
        'If no matching shot exists, rewrite the spoken beat to accurately describe what IS visible '
        'or exclude the claim. Do not create B-roll, fake photographs or generic graphic slides. '
        'Use only IDs from timecoded candidate shot ranges: '+json.dumps(timecodes,ensure_ascii=False)+'. '
        'Output JSON object with fields: '
        'title (Thai); summary (Thai); '
        'scenes: array of objects {id,description,tags} for actually observed candidate shots. '
        'Each description should state observed subject AND action AND setting; tags are Thai visuals. '
        'beats: 5-20 items of {narration,caption,shot_id,visual_keywords,visual_matches}. '
        'Each visual_matches is an array of {id,score,evidence}, sorted by score, '
        'with score between 0 and 1 and a concrete Thai evidence sentence saying WHAT IS VISIBLE '
        'inside that exact shot which supports the ENTIRE narration. '
        'Only include matches scored at least 0.78, no more than 4 per beat; '
        'the first visual_matches.id MUST equal shot_id. Do not assign 0.78 to uncertain shots. '
        'Do not describe video merely from metadata; actually watch the images. '
        'Write each spoken beat to align with that exact visual evidence. '
        'Prefer dynamic original shots and truthful editing over filler. '
        'Make a compelling coherent short video with hook, explanation and resolution, '
        'but only if source footage supports the narrative. '
        f'Target spoken Thai narration approximately {length} seconds, style: {tone}. '
        'Captions concise Thai (max 65 characters), suitable for two-line bold subtitles. '
        'Never use unrelated images just to fill narration time.'
    )


def analyze_proxy(ns, client, proxy, key, source_duration, shots, length, tone):
    import v11
    remote=ns['upload_gemini'](client, proxy, key)
    try:
        # Preserve coverage across the whole input, instead of silently ignoring
        # all later shots when scene detection returns >160 candidates.
        if len(shots)>160:
            idx=sorted({round(i*(len(shots)-1)/159) for i in range(160)})
            candidates=[shots[i] for i in idx]
        else:
            candidates=shots
        timecodes=[{'id':s['id'],'start':s['start'],'end':s['end']} for s in candidates]
        body={'contents':[{'parts':[{'text':make_prompt(timecodes,length,tone)},
            {'fileData':{'mimeType':'video/mp4','fileUri':remote['uri']}}]}],
            'generationConfig':{'responseMimeType':'application/json','temperature':0.10}}
        response=ns['get_json'](client,'POST',f"{ns['BASE']}/models/{ns['MODEL']}:generateContent",key,json=body)
        raw='\n'.join(p.get('text','') for p in response.get('candidates',[{}])[0].get('content',{}).get('parts',[]))
        raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip())
        analysis=json.loads(raw)
        if not isinstance(analysis,dict) or not isinstance(analysis.get('beats'),list) or not analysis['beats']:
            raise RuntimeError('AI ไม่พบฉากจริงที่สัมพันธ์กับเนื้อเรื่องในคลิปที่อัปโหลด')
        analysis['_v14_evidence_required']=True
        analysis['_v14_candidate_shots']=[s['id'] for s in candidates]
        return analysis
    finally:
        try:
            client.delete(f"{ns['BASE']}/{remote['name']}",headers={'x-goog-api-key':key},timeout=15)
        except Exception:
            pass


def normalize(analysis, shots, source_duration, legacy_normalize):
    if not analysis.get('_v14_evidence_required'):
        # Backward compatibility: previously saved V11 checkpoints and offline
        # mocked tests do not have the new evidence schema.
        return legacy_normalize(analysis,shots,source_duration)
    lookup={shot['id']:shot for shot in shots}
    eligible_ids=set(analysis.get('_v14_candidate_shots',[]))
    scenes={x.get('id'):x for x in analysis.get('scenes',[])
            if isinstance(x,dict) and x.get('id') in eligible_ids and isinstance(x.get('description'),str)
            and x['description'].strip()}
    if not scenes:
        raise RuntimeError('AI ไม่ส่งหลักฐานภาพจริงของฉาก กรุณาทดลองอีกครั้ง')
    beats=[];used=set();rejected=[]
    for i,entry in enumerate(analysis.get('beats',[])[:36]):
        if not isinstance(entry,dict):continue
        narration=str(entry.get('narration','')).strip()[:350]
        if len(narration)<3:continue
        valid=[]
        for match in entry.get('visual_matches',[])[:8]:
            if not isinstance(match,dict):continue
            sid=match.get('id')
            evidence=str(match.get('evidence','')).strip()[:300]
            try:score=float(match.get('score',0))
            except (TypeError,ValueError):continue
            # Evidence and image provenance are mandatory: neither a guessed
            # keyword match nor an unverified ID counts as a visual match.
            if sid not in lookup or sid not in scenes or sid not in eligible_ids:continue
            if score<MIN_CONFIDENCE or score>1 or len(evidence)<8:continue
            valid.append((score,sid,evidence))
        if not valid:
            rejected.append({'beat':i,'reason':'no visually evidenced matching shot','narration':narration[:80]})
            continue
        valid.sort(key=lambda e:(e[1] not in used,-e[0]))
        best_sid=valid[0][1]
        chosen=lookup[best_sid]
        caption=str(entry.get('caption') or narration).strip()[:65]
        # Only shots backed by evidence for THIS precise spoken sentence can
        # be used for this beat. V12 allocates these in order and never adds
        # merely lexically similar scenes.
        related=[sid for _score,sid,_evidence in valid]
        b={'narration':narration,'caption':caption,'shot_id':best_sid,
           'source_start':chosen['start'],'source_end':chosen['end'],
           'visual_keywords':[str(x)[:40] for x in entry.get('visual_keywords',[])[:8]],
           'related_shots':related,'visual_match_score':valid[0][0],
           'visual_evidence':valid[0][2]}
        beats.append(b);used.add(best_sid)
    if not beats:
        raise RuntimeError('ไม่มีฉากที่ AI ยืนยันว่าตรงกับคำพากย์ หยุดก่อนสร้างคลิปที่ภาพไม่สัมพันธ์กับเสียง')
    analysis['beats']=beats
    analysis['script']=' '.join(x['narration'] for x in beats)
    analysis['captions']=[x['caption'] for x in beats]
    analysis['highlights']=[{'start':x['source_start'],'end':x['source_end']} for x in beats]
    analysis['visual_matching_report']={'accepted':len(beats),'excluded':len(rejected),
        'excluded_beats':rejected,'algorithm':'video-grounded multimodal shot evidence (topic agnostic)',
        'threshold':MIN_CONFIDENCE}
    return analysis


def install(ns):
    if ns.get('_V14_INSTALLED'):return
    import v11
    old=v11.normalize_beats
    v11.analyze_proxy=analyze_proxy
    v11.normalize_beats=lambda analysis,shots,duration: normalize(analysis,shots,duration,old)
    ns['APP_VERSION']=VERSION
    ns['app'].state.v14_universal_visual_matching=True
    ns['_V14_INSTALLED']=True
    @ns['app'].get('/api/v14/info')
    def info():
        return {'version':VERSION,'visual_match':'evidence from uploaded video, every narration beat',
                'keyword_whitelist':False,'minimum_ai_reported_confidence':MIN_CONFIDENCE,
                'unmatched_beats':'exclude before TTS','guarantee':'AI classification can still be wrong',
                'api_calls':'one Gemini multimodal video analysis; no extra verification call'}
