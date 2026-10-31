"""V22: treat synthetic 6-second partitions as one take; preflight evidence capacity.

Never re-use source frames or pull footage from a visually unsupported take.
This module makes no Gemini API requests.
"""
from __future__ import annotations
import bisect
import math
from pathlib import Path
import re
import subprocess

VERSION='v22-continuous-takes-and-preflight-2026-10-31'


class InsufficientFootage(RuntimeError):
    def __init__(self, index, message):
        self.index=index
        super().__init__(message)


def group_synthetic_shots(shots, proxy, source_duration):
    """Rebuild real scene boundaries from the already reduced proxy.

    v11.detect_shots divides real takes into <=6 second analysis partitions;
    that split is *not* a new camera scene. Cache take IDs with the shots.
    Fail safe when scene analysis cannot complete: keep every partition separate.
    """
    tagged=[dict(s) for s in shots]
    if tagged and all('take_id' in s for s in tagged):
        return tagged
    cuts=[0.]
    try:
        p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(proxy),
            '-vf',"select='gt(scene,0.32)',showinfo",'-an','-f','null','-'],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=360)
        if p.returncode != 0:
            raise RuntimeError('scene detection unsuccessful')
        for found in re.finditer(rb'pts_time:([\d.]+)',p.stderr):
            t=float(found.group(1))
            if 1 < t < source_duration-.5 and t-cuts[-1]>=1.0:
                cuts.append(t)
    except (OSError,RuntimeError,subprocess.TimeoutExpired,ValueError):
        # Cannot prove take continuity, so *do not* claim adjacent ranges are same.
        return [dict(s,take_id=f'isolated_{i}') for i,s in enumerate(tagged)]
    for i,s in enumerate(tagged):
        t=float(s['start']) + min(.01,max(0.,(float(s['end'])-float(s['start']))*.1))
        s['take_id']='take_%04d'%max(0,bisect.bisect_right(cuts,t)-1)
    return tagged


def _glyphs(s):
    return len(re.sub(r'\s+','',str(s)))


def plan(beats, voice_duration, source_duration, shots, windows=None):
    """Allocate one uninterrupted source take per sentence, forward only.

    Only explicitly evidenced shot IDs can anchor a sentence. Their enclosing
    physical take may run up to 4.5 extra seconds beyond the verified segment
    *without a scene cut*. It cannot extend into a different take or rewind.
    """
    import v21_storyflow as v21
    if not beats or voice_duration <=0: raise RuntimeError('ไม่มีประโยคหรือเสียงพากย์')
    if windows is None:
        windows=v21.phrase_windows(beats,voice_duration)
    if len(windows)!=len(beats):raise ValueError('sentence windows do not match beats')
    lookup={str(s['id']):s for s in shots}
    ordered=sorted(shots,key=lambda s:float(s['start']))
    take_end={}
    for s in ordered:
        tid=s.get('take_id',str(s['id']))
        take_end[tid]=max(take_end.get(tid,0.),float(s['end']))
    cursor=-.001
    result=[]
    for i,(beat,(voice_a,voice_b)) in enumerate(zip(beats,windows)):
        needed=float(voice_b)-float(voice_a)
        if needed <=.2 or not math.isfinite(needed):raise InsufficientFootage(i,'ประโยคไม่มีระยะเวลาที่เหมาะสม')
        ids=list(dict.fromkeys([str(beat.get('shot_id',''))]+[str(x) for x in beat.get('related_shots',[])]))
        evidenced=[lookup[x] for x in ids if x in lookup]
        # Related shots count only if AI independently approved the entire beat.
        candidates=[]
        for s in evidenced:
            st=float(s['start']); en=float(s['end']);tid=s.get('take_id',str(s['id']))
            same=[x for x in evidenced if x.get('take_id',str(x['id']))==tid]
            last_verified=max(float(x['end']) for x in same)
            # A short extension stays inside the same camera take, never a new cut.
            permitted_end=min(source_duration,take_end[tid],last_verified+min(4.5,max(.8,(en-st)*.8)))
            a=max(st,cursor)
            if a > en + .001:continue
            if permitted_end-a+1.e-4>=needed:
                candidates.append((a,permitted_end,s))
        if not candidates:
            raise InsufficientFootage(i,
                'ภาพที่ตรวจยืนยันสำหรับประโยคนี้มีความยาวไม่พอ แม้รวมช่วงต่อเนื่องในเทคเดียวแล้ว')
        a,_,chosen=min(candidates,key=lambda x:(x[0],-x[1]))
        remaining=needed;source_at=a;voice_at=float(voice_a)
        while remaining>1.e-5:
            step=min(8.,remaining)
            if 0<remaining-step<.12:step=remaining
            result.append({'source_start':round(source_at,4),'duration':round(step,4),
                'voice_start':round(voice_at,4),'caption':beat.get('caption',beat['narration']),
                'text':beat['narration'],'shot_id':chosen['id'],'v22_forward_continuous':True})
            source_at+=step;voice_at+=step;remaining-=step
        cursor=a+needed
    if abs(sum(x['duration'] for x in result)-voice_duration)>.12:
        raise RuntimeError('ระยะเวลาเสียงกับภาพคลาดเคลื่อน')
    return result


def preflight(result,shots,source_duration):
    """Conservatively fit narration to distinct supported footage *before* TTS.

    Remove whole mid-story sentences rather than clipping words or spending the
    user\'s very limited Gemini TTS quota on an impossible one-minute script.
    """
    beats=list(result.get('beats') or [])
    if not beats:return result
    dropped=[]
    for _ in range(len(beats)):
        seconds=[max(1.5,_glyphs(b.get('narration',''))/7.5) for b in beats]
        windows=[];offset=0.
        for sec in seconds:
            windows.append((offset,offset+sec));offset+=sec
        try:
            plan(beats,offset,source_duration,shots,windows)
            break
        except InsufficientFootage as err:
            if len(beats)<=2:
                raise RuntimeError('ภาพต้นฉบับที่ยืนยันได้ยังไม่พอสำหรับเล่าเรื่องด้วยความเร็วเสียงธรรมชาติ '
                    'หยุดก่อนสร้างเสียงพากย์เพื่อประหยัดโควตา') from err
            # Do not retain an impossible conclusion at the cost of the whole job.
            # Omit the *unallocatable* beat, then keep the remaining story in order.
            index=err.index
            dropped.append(beats.pop(index).get('narration','')[:65])
    result['beats']=beats
    result['script']=' '.join(b['narration'] for b in beats)
    result['captions']=[b.get('caption',b['narration']) for b in beats]
    result['highlights']=[{'start':b['source_start'],'end':b['source_end']} for b in beats
                          if 'source_start' in b and 'source_end' in b]
    result['v22_preflight']={'kept_beats':len(beats),'removed_beats':len(dropped),
       'removed_examples':dropped[:3],'additional_gemini_requests':0,
       'decision':'no loops or unrelated B-roll; conservative natural speech capacity'}
    return result


def install(ns):
    if ns.get('_V22_INSTALLED'):return
    import v11
    import v21_storyflow as v21
    import v17_quality as v17
    previous_detect=v11.detect_shots
    previous_normalize=v11.normalize_beats
    previous_render=v11.render_timeline
    previous_schedule=v21.sequential_shots

    def detect_shots(proxy,duration):
        shots=previous_detect(proxy,duration)
        return group_synthetic_shots(shots,proxy,duration)
    v11.detect_shots=detect_shots

    def normalize_beats(analysis,shots,duration):
        result=previous_normalize(analysis,shots,duration)
        if v21._ACTIVE.get():return preflight(result,shots,duration)
        return result
    v11.normalize_beats=normalize_beats

    def sequential_shots(beats,voice_duration,source_duration,shots,wav=None):
        if not shots or not any('take_id' in s for s in shots):
            return previous_schedule(beats,voice_duration,source_duration,shots,wav)
        return plan(beats,voice_duration,source_duration,shots,
                    v21.phrase_windows(beats,voice_duration,wav))
    v21.sequential_shots=sequential_shots

    def render_timeline(ns1,jid,source,voice,folder,beats,source_duration,
                        source_audio,voice_duration,opts,shots):
        if v21._ACTIVE.get() and int(opts.get('length',30))==60 and not any('take_id' in s for s in shots):
            import json
            proxy=Path(folder)/'analysis_proxy.mp4'
            if proxy.exists():
                shots=group_synthetic_shots(shots,proxy,source_duration)
                if any(str(s.get('take_id','')).startswith('take_') for s in shots):
                    (Path(folder)/'shots-v11.json').write_text(json.dumps(shots,ensure_ascii=False),'utf-8')
        return previous_render(ns1,jid,source,voice,folder,beats,source_duration,
                               source_audio,voice_duration,opts,shots)
    v11.render_timeline=render_timeline
    ns['_V22_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v22_continuous_take_planner=True
    @ns['app'].get('/api/v22/info')
    def info():return {'version':VERSION,'native_take_continuity':True,
          'no_backtrack':True,'max_unverified_extension_seconds':4.5,
          'pre_tts_footage_budget':True,'extra_gemini_requests':0}
