"""V31: evidence-anchored educational illustration, only when strict source planner fails.

A picture can illustrate a Google-grounded fact about the SAME visible subject
without pretending to show an off-camera mechanism. A verified subject anchor is
required; source intervals may be reused transparently ONLY in this fallback.
Never reuse images for events, non-grounded claims, or an unsupported subject.
"""
from __future__ import annotations
import copy
import json
import math
import re
from pathlib import Path

VERSION = 'v31-educational-illustration-fallback-2026-10-31'
DURATIONS = (60, 90, 120)
MAX_CHARS = {60:850, 90:1275, 120:1700}
MIN_SCORE = .78
# Thai word substrings have no whitespace; match specific nouns, not filler.
STOP = {'ภาพ','เรื่อง','ความ','ข้อมูล','วิดีโอ','คลิป','การ','ที่','ใน','จาก','และ','เพื่อ','เกี่ยวกับ','เหตุการณ์','สำคัญ'}
VISUAL_ASSERTIONS = ('ในภาพนี้','กล้องถ่าย','ดังที่เห็นในภาพ','ภาพนี้พิสูจน์','ในวิดีโอเราจะเห็น','อย่างที่เห็นในคลิป')


def glyphs(text):
    return len(re.sub(r'\s+', '', str(text or '')))


def _anchors(raw, shots):
    """Accept only Gemini-reported >=0.78 matches with detailed observed evidence."""
    lookup = {str(s['id']):s for s in shots if isinstance(s,dict) and 'id' in s}
    allowed = set(map(str, raw.get('_v14_candidate_shots') or lookup.keys()))
    scenes = {str(s['id']):s for s in raw.get('scenes',[]) if isinstance(s,dict)
              and str(s.get('id')) in lookup and isinstance(s.get('description'),str)
              and len(s['description'].strip())>=5}
    pool={}
    bybeat=[]
    for beat in (raw.get('beats') or [])[:36]:
        matched=[]
        if not isinstance(beat,dict):
            bybeat.append([]);continue
        for entry in (beat.get('visual_matches') or [])[:8]:
            if not isinstance(entry,dict): continue
            sid=str(entry.get('id',''))
            try:score=float(entry.get('score',0))
            except (ValueError,TypeError):continue
            detail=str(entry.get('evidence','')).strip()
            if not (math.isfinite(score) and MIN_SCORE<=score<=1 and len(detail)>=8):continue
            if sid not in allowed or sid not in scenes:continue
            shot=lookup[sid]
            try:
                a,b=float(shot['start']),float(shot['end'])
            except (KeyError,TypeError,ValueError):continue
            if not (math.isfinite(a) and math.isfinite(b) and b-a>.3):continue
            pool[sid]={'id':sid,'start':a,'end':b,'description':scenes[sid]['description'],
                       'tags':scenes[sid].get('tags',[])}
            matched.append(sid)
        bybeat.append(list(dict.fromkeys(matched)))
    return pool,bybeat


def _subjects(beat):
    out=[]
    for value in beat.get('visual_keywords') or []:
        x=str(value).strip().casefold()
        if len(x)>=3 and x not in STOP and x not in out:out.append(x)
    return out


def _illustrates(beat, anchor):
    words = _subjects(beat)
    if not words:return False
    text=(' '.join([anchor['description']] + [str(x) for x in anchor.get('tags',[])])).casefold()
    narrated=str(beat.get('narration','')).casefold()
    return any(word in text and word in narrated for word in words)


def make_illustrative(raw, shots, target):
    """Factual speech requires citations; footage is an explicitly marked illustration.

    Never use this fallback for undocumented actions or when no match survives.
    """
    if target not in DURATIONS:raise ValueError('Only 60, 90, 120 seconds')
    if not isinstance(raw,dict) or not raw.get('_v14_evidence_required'):
        raise RuntimeError('ไม่พบผลการตรวจภาพจาก Gemini')
    sources = raw.get('knowledge_sources') or []
    if not sources:raise RuntimeError('ไม่มีแหล่งข้อเท็จจริงอ้างอิงจาก Google Search')
    pool, matched = _anchors(raw,shots)
    if not pool:raise RuntimeError('ไม่มีภาพที่ AI ระบุหลักฐานของหัวข้อได้')
    spans = sorted(pool.values(),key=lambda s:s['start'])
    kept=[];rejected=0
    for i,entry in enumerate((raw.get('beats') or [])[:36]):
        if not isinstance(entry,dict):continue
        narration=str(entry.get('narration','')).strip()
        if len(narration)<12 or any(t in narration for t in VISUAL_ASSERTIONS):
            rejected+=1;continue
        direct=matched[i] if i<len(matched) else []
        illustrated=direct or [s['id'] for s in spans if _illustrates(entry,s)]
        # Unmatched facts MUST have a subject keyword in the actual observed shot.
        if not illustrated:
            rejected+=1;continue
        earliest=min((pool[sid]['start'] for sid in illustrated))
        name=str(entry.get('caption') or narration[:40]).strip()[:60]
        kept.append({'narration':narration[:350], 'caption':'ภาพประกอบ • '+name,
             'shot_id':illustrated[0], 'related_shots':list(dict.fromkeys(illustrated)),
             'visual_keywords':_subjects(entry), 'source_start':earliest,
             'source_end':max(pool[sid]['end'] for sid in illustrated),
             '_v31_illustrative':True, '_v31_direct_match':bool(direct)})
    # No filler: a factual, sufficiently long narration is required before TTS.
    minimum={60:600,90:900,120:1200}[target]
    count=sum(glyphs(b['narration']) for b in kept)
    if len(kept)<6 or count<minimum:
        raise RuntimeError(f'ภาพประกอบตรงหัวข้อรองรับบทได้ {len(kept)} ประโยค {count} ตัวอักษร '
              f'ยังไม่พอสำหรับ {target} วินาที ระบบไม่สร้างเสียงหรือต่อเติมข้อเท็จจริงเอง')
    # Preserve opening and conclusion while selecting facts across the complete
    # source; do not speed up a 2-minute script or cut sentences mid-thought.
    if count>MAX_CHARS[target] and len(kept)>=7:
        n=len(kept)
        possible=[]
        for size in range(6,n):
            indexes=sorted({round(i*(n-1)/(size-1)) for i in range(size)})
            selected=[kept[i] for i in indexes]
            size_chars=sum(glyphs(b['narration']) for b in selected)
            if minimum<=size_chars<=MAX_CHARS[target]:
                possible.append((abs(size_chars-int(target*11.8)),size_chars,selected))
        if not possible:
            raise RuntimeError('ไม่สามารถย่อบทให้เหมาะกับความยาวที่เลือกโดยไม่ตัดประโยคหรือแต่งข้อมูล')
        _,count,kept=min(possible,key=lambda row:row[:2])
    if count>MAX_CHARS[target]:
        raise RuntimeError('บทเสียงยาวเกินความยาวที่เลือก และไม่สามารถย่อแบบคงใจความเดิมได้')
    if rejected > len(raw.get('beats') or []):raise AssertionError('invalid beat accounting')
    return {'title':str(raw.get('title',''))[:180],
        'summary':str(raw.get('summary',''))[:1000],
        'beats':kept,'script':' '.join(b['narration'] for b in kept),
        'captions':[b['caption'] for b in kept],
        'highlights':[{'start':b['source_start'],'end':b['source_end']} for b in kept],
        'knowledge_sources':sources,'_v24_knowledge_mode':True,
        '_v17_target_seconds':target,
        'v31_fallback':{'mode':'educational_illustration','visually_verified_anchors':len(pool),
            'accepted_facts':len(kept),'excluded_facts':rejected,
            'spoken_characters':count,
            'caption_discloses_illustration':True,
            'may_reuse_supported_source_images':True,
            'no_external_or_generated_video':True}}


def illustrative_cuts(beats, voice_duration, source_duration, shots, wav=None):
    """All captions are fact/illustration labels, audio windows never overlap.

    Uses a genuine recorded source segment for each cut. Reuse is explicit in
    metadata and only this *educational* mode. Never uses unrelated shots.
    """
    import v21_storyflow as v21
    windows=v21.phrase_windows(beats,voice_duration,wav)
    lookup={str(s['id']):s for s in shots}
    assert len(windows)==len(beats)
    result=[];repeats={}
    for beat,(vs,ve) in zip(beats,windows):
        ids=list(dict.fromkeys(str(x) for x in [beat.get('shot_id')] + list(beat.get('related_shots') or [])))
        choices=sorted([lookup[x] for x in ids if x in lookup],key=lambda x:float(x['start']))
        if not choices:raise RuntimeError('ไม่มีภาพประกอบที่ตรวจสอบได้')
        remain=ve-vs;cursor=vs
        # Choose least-used evidenced source interval; do not trim into other takes.
        while remain>0.00001:
            choice=min(choices,key=lambda s:(repeats.get(str(s['id']),0),float(s['start'])))
            sid=str(choice['id']);a=max(0.,float(choice['start']));end=min(source_duration,float(choice['end']))
            available=end-a
            if available<.20:raise RuntimeError('ภาพต้นฉบับสำหรับประกอบสั้นเกินไป')
            take=min(remain,available,8.)
            if 0<remain-take<.12:take=remain
            # A subshot can start later inside same source to vary repeated frame ranges.
            used=repeats.get(sid,0)
            if take<=available:
                source_start=a+(max(0.,available-take)*(used % 3)/2.)
            else:source_start=a
            if source_start+take>end+.005:raise RuntimeError('ภาพประกอบเกินขอบเขตต้นฉบับ')
            result.append({'source_start':round(source_start,5),'duration':round(take,5),
                  'voice_start':round(cursor,5),'caption':beat['caption'],
                  'text':beat['narration'],'shot_id':sid,
                  '_v31_illustrative':True,'_v31_repeat_index':used})
            repeats[sid]=used+1;cursor+=take;remain-=take
    if abs(sum(x['duration'] for x in result)-voice_duration)>.12:
        raise RuntimeError('ภาพประกอบและเสียงพากย์มีระยะเวลาไม่ตรงกัน')
    return result


def install(ns):
    if ns.get('_V31_INSTALLED'):return
    import v11, v14_semantic as v14
    import v30_source_first as v30
    previous_normalize=v11.normalize_beats
    previous_time_beats=v11.time_beats
    previous_process=ns['process']
    # Change only the educational prompt so model can separate factual grounding
    # from source footage used as same-subject illustration. Model still supplies
    # visible evidence and score per shot. This is not an evidence-score bypass.
    previous_prompt=v14.make_prompt
    def prompt(tc,length,tone):
        old=previous_prompt(tc,length,tone)
        if 'สาระน่ารู้' not in str(tone):return old
        return old + ('\nV31 EDUCATIONAL MODE: Distinguish independently Google-grounded facts '
           'from footage evidence. A fact about a distinctive visible subject can '
           'use actual shots OF THAT SAME SUBJECT as transparent illustrative B-roll. '
           'The camera need not reveal an invisible scientific explanation. '
           'For each relevant source shot specify real observed subject, setting, '
           'action, and a visual_matches evidence sentence about the SUBJECT visibly '
           'present, not falsely claiming the entire external fact was captured. '
           'Score >=0.78 ONLY if the distinctive actual subject truly matches; '
           'do not add a score for loosely related generic footage. '
           'Include visual_keywords with exact subject names that also appear '
           'in your scenes[].description/tags. Every narration beat should '
           'be a complete Thai fact grounded in Google Search; avoid claims '
           'such as "we see" unless directly filmed. '
           'Describe candidate source scenes across the whole video. '
           'If strict frame-by-frame alignment is impossible, a clearly labeled '
           'illustrative edit can show source shots again with different trims, '
           'without pretending the clip is original new footage. Do not invent facts.')
    v14.make_prompt=prompt

    def normalize(raw,shots,source_duration):
        original_model_result=copy.deepcopy(raw)
        try:return previous_normalize(raw,shots,source_duration)
        except RuntimeError as original:
            # Never bypass Gemini quota/API failures, TTS failures or FFmpeg errors.
            # V24 pre-TTS visual refusal mentions TTS even though no voice API ran.
            pre_tts_visual_refusal=str(original).startswith(
                'ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที ไม่เรียก TTS')
            # No bypass for Gemini quota, real TTS, HTTP errors or FFmpeg.
            if not (v30.need_deep_repair(original) or pre_tts_visual_refusal):raise
            job=v30._JOB.get()
            if not job or 'สาระน่ารู้' not in str(job['opts'].get('tone','')):
                raise
            target=int(job['opts'].get('length',60))
            if target not in DURATIONS:raise
            folder=Path(ns['WORK'])/job['jid']
            deep=folder/'analysis-deep-v30.json'
            candidate=original_model_result
            if deep.is_file():
                try:
                    d=json.loads(deep.read_text('utf-8'))
                    if isinstance(d,dict) and d.get('knowledge_sources') and d.get('beats'):
                        candidate=d
                except (OSError,ValueError):pass
            try:
                result=make_illustrative(candidate,shots,target)
            except RuntimeError as fallback_error:
                raise RuntimeError(str(original)[:180]+' | โหมดภาพประกอบยังไม่ผ่าน: '+str(fallback_error)[:260]) from fallback_error
            ns['notify'](job['jid'],43,'เลือกภาพประกอบหัวข้อเดียวกันจากต้นฉบับ พร้อมป้ายภาพประกอบ')
            return result

    def time_beats(beats,duration,source_duration,shots):
        if beats and beats[0].get('_v31_illustrative'):
            import v21_storyflow as v21
            ctx=v21._RENDER.get() or {}
            return illustrative_cuts(beats,duration,source_duration,shots,ctx.get('voice'))
        return previous_time_beats(beats,duration,source_duration,shots)

    def process(jid,src_path,link,key,opts):
        result=previous_process(jid,src_path,link,key,opts)
        folder=Path(ns['WORK'])/jid
        afile=folder/'analysis-v11.json'
        if afile.is_file():
            try:
                data=json.loads(afile.read_text('utf-8'))
                if isinstance(data.get('v31_fallback'),dict):
                    with ns['lock']:
                        status=ns['jobs'].get(jid)
                        if status is not None and status.get('state')=='done':
                            status['mode_note']='สาระน่ารู้: ภาพประกอบจากคลิปต้นฉบับ (อาจใช้ภาพช่วงเดิมซ้ำ โดยระบุบนซับ) พร้อมข้อเท็จจริงจากแหล่งอ้างอิง'
                            status['v31_illustrative']=True
                            ns['save_job'](jid)
            except (OSError,ValueError):pass
        return result

    ns['process']=process
    v11.normalize_beats=normalize
    v11.time_beats=time_beats
    ns['_V31_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v31_grounded_educational_illustration=True
    @ns['app'].get('/api/v31/info')
    def info():
        return {'version':VERSION,'for_mode':'สาระน่ารู้','fallback_only_after_strict_failure':True,
            'minimum_model_visual_confidence':.78,'facts_must_have_search_sources':True,
            'source_images_may_repeat_with_disclosure':True,'unrelated_images':False,
            'cannot_guarantee_all_videos_have_sufficient_facts':True}
