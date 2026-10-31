"""V25: forward-only, take-aware, quota-conservative visual capacity repair.

A verified original shot anchors each complete Thai sentence.  Its physical
camera take can continue beyond a synthetic six-second analysis partition,
without crossing detected actual cuts, looping, or selecting unrelated images.
No added Gemini request.  Refuse when evidence really is insufficient.
"""
from __future__ import annotations
from functools import lru_cache
import math
import re

VERSION = 'v25-evidence-aware-adaptive-take-planner-2026-10-31'
MAX_TAKE_EXTENSION = 12.0
DURATION_OPTIONS = (60, 90, 120)


def _glyphs(value):
    return len(re.sub(r'\s+', '', str(value or '')))


def _take_lookup(shots):
    take_ends = {}
    for shot in shots:
        t = str(shot.get('take_id', 'isolated_'+str(shot['id'])))
        take_ends[t] = max(take_ends.get(t, 0.0), float(shot['end']))
    return take_ends


def _verified_takes(beats, shots, duration):
    lookup = {str(s['id']):s for s in shots}
    ends = _take_lookup(shots)
    items = {}
    for beat in beats:
        seen = [beat.get('shot_id')] + list(beat.get('related_shots') or [])
        for sid in seen:
            s = lookup.get(str(sid))
            if not s: continue
            take = str(s.get('take_id', 'isolated_'+str(s['id'])))
            observed_end = max(float(lookup[str(x)]['end']) for x in seen if str(x) in lookup and
                               str(lookup[str(x)].get('take_id','isolated_'+str(x))) == take)
            end = min(float(duration), ends[take], observed_end+MAX_TAKE_EXTENSION)
            start = max(0.0,float(s['start']))
            if end - start > 0.2:
                old = items.get(take)
                items[take] = (min(start, old[0]), max(end, old[1])) if old else (start,end)
    return items


def plan(beats, voice_duration, source_duration, shots, windows=None):
    """Search verified non-overlapping source takes without greedy false negatives."""
    import v22_scene as v22
    import v21_storyflow as v21
    if not beats or not math.isfinite(float(voice_duration)) or voice_duration <= 0:
        raise RuntimeError('ไม่มีประโยคหรือเสียงพากย์ที่ใช้ได้')
    if windows is None:
        windows=v21.phrase_windows(beats,voice_duration)
    if len(windows)!=len(beats):
        raise ValueError('จำนวนช่วงเสียงไม่ตรงกับประโยค')
    lookup={str(s['id']):s for s in shots}
    take_end=_take_lookup(shots)
    choices=[]
    for i, (beat,(vstart,vend)) in enumerate(zip(beats,windows)):
        need=float(vend)-float(vstart)
        if need<=.15 or not math.isfinite(need):
            raise v22.InsufficientFootage(i,'ความยาวประโยคไม่ถูกต้อง')
        ids=list(dict.fromkeys(str(x) for x in [beat.get('shot_id')]+list(beat.get('related_shots') or [])))
        verified_by_take={}
        for sid in ids:
            s=lookup.get(sid)
            if not s:continue
            take=str(s.get('take_id', 'isolated_'+str(s['id'])))
            verified_by_take[take]=max(verified_by_take.get(take,0.),float(s['end']))
        candidates=[]
        for sid in ids:
            s=lookup.get(sid)
            if not s:continue
            take=str(s.get('take_id','isolated_'+str(s['id'])))
            # Expansion is allowed ONLY within a physically continuous camera take.
            # No extension beyond a real cut, no cross-topic footage, no rewinding.
            stop=min(float(source_duration),take_end[take],verified_by_take[take]+MAX_TAKE_EXTENSION)
            start=max(0.,float(s['start']))
            if stop-start+.001>=need:
                candidates.append((start,stop,sid))
        candidates.sort(key=lambda x:(x[0],-x[1],x[2]))
        choices.append((need,float(vstart),candidates))

    deepest=[0]
    @lru_cache(maxsize=60000)
    def search(index,cursor):
        deepest[0]=max(deepest[0],index)
        if index==len(choices):return ()
        need,_,candidates=choices[index]
        for st,stop,sid in candidates:
            first=max(st,cursor)
            if stop-first+.0001<need:continue
            next_cursor=round(first+need,6)
            rest=search(index+1,next_cursor)
            if rest is not None:
                return ((first,need,sid),)+rest
        return None
    allocation=search(0,0.0)
    if allocation is None:
        i=min(len(beats)-1,deepest[0])
        raise v22.InsufficientFootage(i,
            'ไม่มีช่วงภาพที่ตรงกับประโยคยาวพอในเทคจริงโดยไม่ย้อนภาพหรือข้ามฉาก')
    result=[]
    for beat,(vstart,vend),(start,need,sid) in zip(beats,windows,allocation):
        local=0.0
        while local<need-.00001:
            take=min(8.0,need-local)
            if need-local-take<.12:take=need-local
            result.append({'source_start':round(start+local,4),
                           'duration':round(take,4),
                           'voice_start':round(float(vstart)+local,4),
                           'caption':beat.get('caption') or beat['narration'],
                           'text':beat['narration'], 'shot_id':sid,
                           'v25_forward_continuous':True})
            local+=take
    if abs(sum(x['duration'] for x in result)-float(voice_duration))>.12:
        raise RuntimeError('เวลาเสียงและภาพคลาดเคลื่อน')
    if any(b['source_start']+.001<a['source_start']+a['duration'] for a,b in zip(result,result[1:])):
        raise RuntimeError('ระบบตรวจพบภาพย้อนหลังและหยุดเพื่อป้องกันภาพวน')
    return result


def preflight(result,shots,source_duration):
    """Try all supported takes and preserve a usable script rather than dropping to 2 beats.

    Whole-phrase pruning is permitted only when the selected output still has
    enough substantive narration to reach the desired minimum naturally.
    """
    import v22_scene as v22
    beats=list(result.get('beats') or [])
    if not beats:return result
    target=int(result.get('_v17_target_seconds') or 60)
    if target not in DURATION_OPTIONS:target=60
    removed=[]
    floor={60:420,90:625,120:830}[target]
    for _ in range(len(beats)):
        lengths=[max(1.5,_glyphs(x.get('narration'))/7.5) for x in beats]
        total=sum(lengths)
        windows=[]
        offset=0.0
        for sec in lengths:
            windows.append((offset,offset+sec));offset+=sec
        try:
            plan(beats,total,source_duration,shots,windows)
            break
        except v22.InsufficientFootage as exc:
            at=exc.index
            if at<=0 or at>=len(beats)-1 or len(beats)<6:
                raise RuntimeError(
                    f'ต้นฉบับยาว {source_duration:.1f} วินาที แต่ภาพที่ AI จับคู่ประโยคที่ {at+1} '
                    'ยังไม่เพียงพอแม้ใช้ช่วงเทคจริงแล้ว กรุณาเลือกคลิปที่มีภาพเกี่ยวข้องมากขึ้น '
                    'หรือลองวิดีโอฉบับที่มีหลายช่วงเหตุการณ์ (ยังไม่เรียก Gemini TTS)') from exc
            if sum(_glyphs(b.get('narration')) for i,b in enumerate(beats) if i!=at)<floor:
                raise RuntimeError(
                    'ช่วงภาพที่ AI ยืนยันได้มีน้อยกว่าที่ต้องใช้สำหรับคลิปอย่างน้อยหนึ่งนาที '
                    'และไม่สามารถตัดบทเพิ่มโดยไม่ทำให้คลิปสั้นกว่าที่เลือก '
                    'ระบบหยุดก่อนเรียก Gemini TTS เพื่อประหยัดโควตา') from exc
            removed.append(beats.pop(at).get('narration','')[:80])
    total_chars=sum(_glyphs(x.get('narration')) for x in beats)
    # V17 can yield 430-700 chars for 60s. Avoid pretending a 2-beat script
    # reaches a minute merely by adding silence.
    if total_chars<floor:
        raise RuntimeError(f'มีบทพูดที่ภาพยืนยันได้เพียง {total_chars} ตัวอักษร '
                           f'แต่โหมด {target} วินาทีต้องใช้บทที่สมบูรณ์กว่านี้')
    result['beats']=beats
    result['script']=' '.join(b['narration'] for b in beats)
    result['captions']=[b.get('caption',b['narration']) for b in beats]
    result['highlights']=[{'start':b['source_start'],'end':b['source_end']} for b in beats
                          if 'source_start' in b and 'source_end' in b]
    result['v25_preflight']={'kept_beats':len(beats),'removed_beats':len(removed),
                             'removed_examples':removed[:2],
                             'verified_takes':len(_verified_takes(beats,shots,source_duration)),
                             'estimated_spoken_seconds':round(sum(max(1.5,_glyphs(b['narration'])/7.5) for b in beats),1),
                             'max_take_extension':MAX_TAKE_EXTENSION,
                             'extra_gemini_requests':0,
                             'no_repeat':True}
    return result


def install(ns):
    if ns.get('_V25_INSTALLED'):return
    import v22_scene as v22
    import v14_semantic as v14
    previous_prompt=v14.make_prompt
    def prompt(timecodes,length,tone):
        return previous_prompt(timecodes,length,tone) + (
            '\nV25 STRICT EDITING HINTS: Ground at least one short, complete and '
            'meaningful Thai narration beat in EACH DIFFERENT actual camera take '
            'needed to cover the chosen duration. Plan each beat to take 3-7 '
            'seconds to speak NATURALLY. Do not use a 15-second sentence with '
            'a 4-second source scene; break long ideas into distinct complete '
            'sentences, each separately visually verified with an appropriate '
            'real take. Label each match with its true source shot ID, include '
            'other independently verified related shots only when they visibly '
            'support the same entire beat. Keep all source timestamps ascending '
            'and never revisit shots. If there are insufficient distinct '
            'original takes, do not fabricate extras. In educational mode, '
            'use same-topic footage as ILLUSTRATION for Google-grounded facts, '
            'but do not falsely claim offscreen scientific details are visible. '
            'Ensure enough meaningful full sentences for the minimum selected '
            'minute; no generic filler, fake urgency or unsupported claims.'
        )
    v14.make_prompt=prompt
    v22.plan=plan
    v22.preflight=preflight
    ns['APP_VERSION']=VERSION
    ns['_V25_INSTALLED']=True
    ns['app'].state.v25_adaptive_source_takes=True
    ns['app'].state.v25_bounded_extension_seconds=MAX_TAKE_EXTENSION
    @ns['app'].get('/api/v25/info')
    def info():
        return {'version':VERSION,'forward_only':True,'no_loop':True,
                'max_extension_same_camera_take_seconds':MAX_TAKE_EXTENSION,
                'pre_tts_source_capacity_validation':True,
                'extra_gemini_requests':0}
