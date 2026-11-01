"""V33: bounded recovery of *already returned* video-grounded model replies.

Does not infer unseen footage or synthesize facts. Combines only separately grounded
model narration and Gemini-reported visual evidence from the user's same source.
A failed 60s target is reported honestly, rather than skipping 28% silently.
"""
from __future__ import annotations
import copy
import json
import math
import re
from pathlib import Path

VERSION='v33-cross-pass-grounded-story-recovery-2026-11-01'


def _subject_count(beat):
    return len([x for x in (beat.get('visual_keywords') or []) if isinstance(x,str) and len(x.strip())>=3])


def merge_grounded_responses(initial, folder, shots):
    """Combine only full model outputs that carry their OWN external citations.

    No fabricated timestamps, synthetic matches, citations or video segments.
    Avoid cross-source citation laundering: use independent citations and only
    the beats that individually come from a cited model response.
    """
    import v32_recovery as v32
    lookup={str(s['id']):s for s in shots if isinstance(s,dict) and 'id' in s}
    source_replies=list(v32.read_candidates(initial,folder))
    metadata={'sources_examined':len(source_replies),'grounded_sources':0,
              'candidate_beats':0,'merged_beats':0,'valid_direct_anchors':0,
              'distinct_direct_shots':0,'estimated_evidence_seconds':0.0}
    citations=[]; scenes={}; beat_rows=[]; seen=set(); matched=set()
    for label,raw in source_replies:
        if not isinstance(raw,dict) or not raw.get('_v14_evidence_required'):continue
        ref=raw.get('knowledge_sources') or []
        if not isinstance(ref,list) or not ref:continue
        metadata['grounded_sources']+=1
        local_scenes={}
        for s in raw.get('scenes') or []:
            if not isinstance(s,dict):continue
            sid=str(s.get('id',''))
            description=str(s.get('description','')).strip()
            if sid in lookup and len(description)>=5:
                local_scenes[sid]=s
        allowed=set(map(str,raw.get('_v14_candidate_shots') or lookup.keys()))
        for x in ref[:25]:
            if isinstance(x,dict) and (x.get('url') or x.get('uri')):
                if x not in citations:citations.append(copy.deepcopy(x))
        for ix,beat in enumerate((raw.get('beats') or [])[:36]):
            if not isinstance(beat,dict):continue
            narration=str(beat.get('narration','')).strip()
            if len(narration)<12:continue
            metadata['candidate_beats']+=1
            key=re.sub(r'\s+','',narration).casefold()
            if key in seen:continue
            matches=[]
            for m in (beat.get('visual_matches') or [])[:8]:
                if not isinstance(m,dict):continue
                sid=str(m.get('id',''))
                try:score=float(m.get('score',0))
                except (ValueError,TypeError):continue
                ev=str(m.get('evidence','')).strip()
                if not (sid in lookup and sid in allowed and sid in local_scenes
                        and math.isfinite(score) and 0.78<=score<=1 and len(ev)>=8):continue
                matches.append(copy.deepcopy(m));matched.add(sid)
                if sid not in scenes:scenes[sid]=copy.deepcopy(local_scenes[sid])
            if not matches:
                # Unmatched beat can be used only if V31 validates that the
                # distinctive subject of a verified anchor is genuinely visible.
                if not _subject_count(beat):continue
            entry=copy.deepcopy(beat)
            entry['visual_matches']=matches
            if matches:entry['shot_id']=matches[0]['id']
            beat_rows.append((label,ix,entry));seen.add(key)
    metadata['valid_direct_anchors']=sum(bool(b['visual_matches']) for _,_,b in beat_rows)
    metadata['distinct_direct_shots']=len(matched)
    metadata['estimated_evidence_seconds']=round(sum(max(0.,float(lookup[s]['end'])-float(lookup[s]['start'])) for s in matched),1)
    metadata['merged_beats']=min(36,len(beat_rows))
    if not citations or not matched or not beat_rows:return None,metadata
    # Story order: preserve each supplied model's order; group by initial
    # source chronology, then use subsequent model descriptions to enrich.
    # No mixing chunks of unrelated video sources: all refer to this job's shots.
    rows=beat_rows[:36]
    combined={
        'title':str(initial.get('title',''))[:180],
        'summary':str(initial.get('summary',''))[:1000],
        '_v14_evidence_required':True,
        '_v14_candidate_shots':sorted(set(lookup)),
        'knowledge_sources':citations,
        'scenes':list(scenes.values()),
        'beats':[b for _,_,b in rows],
    }
    return combined,metadata


def install(ns):
    if ns.get('_V33_INSTALLED'):return
    import v11, v30_source_first as v30, v31_illustrative as v31, v32_recovery as v32
    prior=v11.normalize_beats

    def normalize(raw,shots,source_duration):
        original=copy.deepcopy(raw)
        try:
            return prior(raw,shots,source_duration)
        except RuntimeError as exc:
            # V32 emits its own final visual refusal after evaluating all passes.
            # That report is also a *pre-TTS* planning error, not an API fault.
            visual_refusal=(v32.visual_planning_failure(exc) or
                str(exc).startswith('ตรวจภาพและบทครบทั้งรอบแรก รอบวางบทใหม่ และรอบลึกแล้ว'))
            if not visual_refusal:raise
            context=v30._JOB.get()
            if not isinstance(context,dict):raise
            opts=context.get('opts') or {}
            # Knowledge fallback must never silently change news/event tone
            # or use ungrounded narration from unrelated subjects.
            if 'สาระน่ารู้' not in str(opts.get('tone','')):raise
            target=int(opts.get('length',60))
            if target not in (60,90,120):raise
            folder=Path(ns['WORK']) / str(context['jid'])
            merged,summary=merge_grounded_responses(original,folder,shots)
            if merged is None:
                v11.atom_json(folder/'v33-coverage.json',dict(summary,status='no_grounded_merge'))
                raise RuntimeError('V33: ผลวิเคราะห์ยังไม่มีหลักฐานภาพและแหล่งอ้างอิงเพียงพอ '
                                   f'(ภาพยืนยัน {summary["distinct_direct_shots"]} ช็อต, '
                                   f'บททั้งหมด {summary["candidate_beats"]} ประโยค) '
                                   'ไม่สร้างบทหรือภาพที่ไม่มีหลักฐาน') from exc
            try:
                result=v31.make_illustrative(merged,shots,target)
            except (RuntimeError,ValueError) as err:
                v11.atom_json(folder/'v33-coverage.json',dict(summary,status='insufficient_verified_narration',
                                    reason_code=type(err).__name__))
                raise RuntimeError('V33: รวมผลวิเคราะห์ที่มีแหล่งอ้างอิงทั้งหมดแล้ว '
                                   f'แต่ยังมีภาพยืนยัน {summary["distinct_direct_shots"]} ช็อต '
                                   f'({summary["estimated_evidence_seconds"]} วินาทีในต้นฉบับ) '
                                   f'และบทที่เกี่ยวข้องยังไม่พอสำหรับ {target} วินาที '
                                   'จึงหยุดก่อนสร้างเสียง ไม่แต่งเรื่องหรือวนภาพโดยไม่แจ้ง') from err
            result['v33_recovery']={
                'source':'grounded-original-plus-replans',
                'selected_grounded_sources':summary['grounded_sources'],
                'distinct_direct_shots':summary['distinct_direct_shots'],
                'no_new_api_calls':True, 'evidence_is_model_report_not_independent':True,
                'original_source_only':True}
            v11.atom_json(folder/'v33-coverage.json',dict(summary,status='selected'))
            ns['notify'](context['jid'],43,'เรียงบทจากหลักฐานที่บันทึกไว้หลายรอบโดยไม่เรียก Gemini ซ้ำ')
            return result
    v11.normalize_beats=normalize
    ns['_V33_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v33_multi_analysis_recovery=True
    @ns['app'].get('/api/v33/info')
    def info():
        return {'version':VERSION,'mode':'สาระน่ารู้',
                'recovery':'grounded-existing-checkpoints-only',
                'no_paid_retry':True,'only_model_confirmed_source_shots':True,
                'no_guarantee_for_insufficient_actual_content':True}
