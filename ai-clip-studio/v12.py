"""AI Clip Studio V12: semantic shot-capacity repair.

A single relevant shot is allowed to be reused, deliberately, only when all
non-overlapping relevant source intervals have been exhausted. This avoids a
late rendering failure without inserting unrelated imagery. When possible,
script is shortened before TTS to match unique footage.
"""
from __future__ import annotations
import math
import re
from typing import Any

VERSION='v12-semantic-capacity-repair-2026-10-30'


def _match_keywords(beat, scene):
    keys=[str(x).strip().lower() for x in beat.get('visual_keywords',[]) if str(x).strip()]
    text=(' '.join([str(scene.get('description',''))]+[str(x) for x in scene.get('tags',[])])).lower()
    return sum(min(len(k),12) for k in keys if k in text)


def _eligible_shots(beat, shots, descriptions):
    lookup={s['id']:s for s in shots}
    preferred=lookup.get(beat['shot_id'])
    if not preferred:
        raise ValueError('Beat has no grounded primary video shot')
    scored=[]
    for shot in shots:
        if shot['id']==preferred['id']:
            continue
        score=_match_keywords(beat, descriptions.get(shot['id'],{}))
        if score>0:
            scored.append((score,shot))
    scored.sort(key=lambda x:(-x[0],abs(x[1]['start']-preferred['start'])))
    return [preferred]+[x[1] for x in scored]


def install(ns):
    if ns.get('_V12_INSTALLED'):return
    import v11
    base_normalize=v11.normalize_beats
    def normalize_with_related(analysis,shots,source_duration):
        result=base_normalize(analysis,shots,source_duration)
        descriptions={x['id']:x for x in result.get('scenes',[]) if isinstance(x,dict) and 'id' in x}
        for beat in result['beats']:
            eligible=_eligible_shots(beat,shots,descriptions)
            beat['related_shots']=[s['id'] for s in eligible]
            # If video offers only a short clip for this beat, prefer the shorter
            # caption to avoid producing lengthy voiceover for a tiny scene.
            # Leave already-short narration unchanged.
            seconds=sum(max(0,float(s['end'])-float(s['start'])) for s in eligible)
            narration=beat['narration']
            caption=beat.get('caption','')
            guessed_seconds=len(re.sub(r'\s+','',narration))/5.0
            if caption and 3<=len(caption)<len(narration) and guessed_seconds>seconds*1.10:
                beat['narration']=caption
        result['script']=' '.join(x['narration'] for x in result['beats'])
        return result

    def allocate_with_reuse(beats,voice_duration,source_duration,shots):
        """Schedule all narration while favoring unique relevant video.

        Reuses a *relevant* original source interval only as a last resort;
        never silently fills voice time with unrelated B-roll or black screen.
        """
        if not beats or not math.isfinite(voice_duration) or voice_duration<=0:
            raise RuntimeError('ไม่มีเสียงพากย์หรือรายการฉากที่ใช้ได้')
        lookup={s['id']:s for s in shots}
        weights=[max(6,len(re.sub(r'\s+','',b['narration']))) for b in beats]
        total=sum(weights)
        durations=[voice_duration*w/total for w in weights]
        # Set last target to remaining duration; avoid accumulating tiny drift.
        durations[-1]=voice_duration-sum(durations[:-1])
        used=[]
        cuts=[]
        offset=0.0
        max_chunk=v11.SEGMENT_MAX_SECONDS
        def free_intervals(start,end):
            pool=[(start,end)]
            for lo,hi in used:
                nxt=[]
                for a,b in pool:
                    if hi<=a or lo>=b:nxt.append((a,b))
                    else:
                        if a<lo:nxt.append((a,lo))
                        if hi<b:nxt.append((hi,b))
                pool=nxt
            return pool
        def append_chunk(a,d,b,*,repeat=False):
            nonlocal offset
            if d<.09:return
            while d>.0001:
                chunk=min(d,max_chunk)
                if chunk<.09:
                    # Avoid extremely short video packets by extending previous
                    # same-shot segment only when source still has space.
                    if cuts and cuts[-1]['shot_id']==b['shot_id'] and cuts[-1]['duration']+chunk<=max_chunk:
                        cuts[-1]['duration']=round(cuts[-1]['duration']+chunk,4)
                        offset+=chunk
                    else:
                        # Put tiny tail onto previous segment (audio remains continuous).
                        if cuts:
                            cuts[-1]['duration']=round(cuts[-1]['duration']+chunk,4)
                            offset+=chunk
                    return
                cuts.append({'source_start':round(a,4),'duration':round(chunk,4),
                    'voice_start':round(offset,4),'caption':b.get('caption',b['narration']),
                    'text':b['narration'],'shot_id':b['shot_id'],
                    'reused_related_footage':repeat})
                offset+=chunk
                a+=chunk
                d-=chunk
        for i,(beat,need) in enumerate(zip(beats,durations)):
            if need<.09:continue
            choices=[lookup.get(sid) for sid in beat.get('related_shots',[]) if sid in lookup]
            if not choices:
                choices=[s for s in shots if s['id']==beat.get('shot_id')]
            choices=[s for s in choices if s and float(s['end'])-float(s['start'])>=.15]
            if not choices:
                raise RuntimeError('ไม่มีภาพต้นฉบับที่ตรงกับบทพากย์ในช่วงนี้')
            remaining=need
            for shot in choices:
                if remaining<=.001:break
                a=max(0,float(shot['start']));z=min(source_duration,float(shot['end']))
                for lo,hi in free_intervals(a,z):
                    if remaining<=.001:break
                    take=min(remaining,hi-lo)
                    if take<.09:continue
                    append_chunk(lo,take,beat)
                    used.append((lo,lo+take))
                    remaining-=take
            # Final safety net: repeat only relevant, verified original footage,
            # in short pieces rather than fail at 63% after TTS was paid for.
            if remaining>.001:
                loops=0
                while remaining>.001:
                    shot=choices[loops%len(choices)]
                    start=max(0.0,float(shot['start']))
                    available=min(source_duration,float(shot['end']))-start
                    if available<.15:raise RuntimeError('ภาพต้นฉบับที่เกี่ยวข้องสั้นเกินไป')
                    take=min(remaining,available,max_chunk)
                    if take<.09 and cuts:
                        cuts[-1]['duration']=round(cuts[-1]['duration']+take,4)
                        offset+=take
                    else:append_chunk(start,take,beat,repeat=True)
                    remaining-=take
                    loops+=1
                    if loops>2000:raise RuntimeError('ระยะเวลาเสียงพากย์ไม่สมเหตุสมผล')
        if not cuts:raise RuntimeError('ไม่สามารถสร้างไทม์ไลน์จากภาพต้นฉบับ')
        if abs(offset-voice_duration)>.08:raise RuntimeError('ระยะเวลาเสียงกับภาพไม่ตรงกัน')
        return cuts

    v11.normalize_beats=normalize_with_related
    v11.time_beats=allocate_with_reuse
    ns['APP_VERSION']=VERSION
    ns['app'].state.v12_capacity_fallback=True
    ns['app'].state.v12_source_only=True
    ns['_V12_INSTALLED']=True
