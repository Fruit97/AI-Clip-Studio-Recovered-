"""V35: context-safe continuity for sparse shots in long stationary recordings.

The error '8/8 with 47.7 source partition seconds' does not mean the real video
contains only 47.7 s. A physical camera take can extend well beyond synthetic
6-second partitions. Only Gemini-proven narration/anchors are preserved.
"""
from __future__ import annotations
import contextvars
import copy
import json
import math
import re
from pathlib import Path

VERSION = 'v35-source-continuity-verified-evidence-2026-11-01'
_ACTIVE = contextvars.ContextVar('v35_job', default=None)
TARGETS = {60:490, 90:705, 120:940}
FORBIDDEN = ('gemini api (', 'http 429','http 503','quota exceeded',
             'gemini tts error','ffmpeg:', 'read timeout','api key', 'ไฟล์เสียงพากย์')


def eligible_failure(exc):
    import v32_recovery
    return (isinstance(exc, RuntimeError)
            and not any(w in str(exc).casefold() for w in FORBIDDEN)
            and v32_recovery.visual_planning_failure(exc))


def candidates(raw, folder):
    yield 'initial', copy.deepcopy(raw)
    for label,name in [('replanned-v27','analysis-replanned-v27.json'),
                       ('deep-v30','analysis-deep-v30.json')]:
        try:
            item = json.loads((Path(folder)/name).read_text(encoding='utf-8'))
            if isinstance(item, dict) and isinstance(item.get('beats'),list):
                yield label,item
        except (OSError, ValueError, UnicodeError):
            pass


def glyphs(beats):
    return sum(len(re.sub(r'\s+','',str(b.get('narration','')))) for b in beats)


def takes(shots, duration):
    """Use V22 verified physical take IDs, never join across detected camera cuts.

    Unknown IDs are treated as isolated 6-second slices; no false continuity.
    """
    bounds={}
    for s in shots:
        try:
            a=max(0.,float(s['start']));b=min(float(duration),float(s['end']))
        except (KeyError, ValueError, TypeError):continue
        if not(math.isfinite(a) and math.isfinite(b) and b>a+.15):continue
        sid=str(s.get('id',''))
        tid=str(s.get('take_id') or 'isolated_'+sid)
        if tid in bounds:
            lo,hi=bounds[tid];bounds[tid]=(min(lo,a),max(hi,b))
        else:bounds[tid]=(a,b)
    return bounds


def select_grounded(raw,folder,shots,source_duration,target,tone=""):
    """Do not invent visual matches, sentences, cited sources or confidence.

    Use all 3 existing checkpoint candidates, including V27 when its 8/8 is
    stronger than the initial 3/7. For normal modes, external claims remain
    limited to the model's actual video analysis.
    """
    import v14_semantic as v14
    import v17_quality as v17
    import v28_alignment as v28
    import v21_storyflow as v21
    bounds=takes(shots,source_duration)
    lookup={str(s.get('id')):s for s in shots if isinstance(s,dict)}
    options=[];diagnostics=[]
    for name,item in candidates(raw,folder):
        try:
            if not item.get('_v14_evidence_required'):
                raise ValueError('no explicit source evidence')
            if 'สาระน่ารู้' in str(tone) and not item.get('knowledge_sources'):
                raise ValueError('knowledge mode requires original Google grounding')
            # THIS helper is V14's true strict evidence filter, not a fabricated
            # inferred match. Do not call previous V26 preflight here: that is
            # exactly the hard-partition assumption being repaired.
            result=v14.normalize(copy.deepcopy(item),shots,source_duration,
                                  lambda value,_shots,_duration:value)
            result=v21.polish_story(result)
            if target==60:
                result=v17.enforce_script_budget(result,target)
            bs=list(result.get('beats') or [])
            if len(bs)<3 or glyphs(bs)<TARGETS[target]:
                raise RuntimeError('insufficient supported natural spoken content')
            direct=set();chosen_takes=set()
            for beat in bs:
                ids=[beat.get('shot_id')]+list(beat.get('related_shots') or [])
                for sid in ids:
                    shot=lookup.get(str(sid))
                    if not shot:continue
                    direct.add(str(sid))
                    chosen_takes.add(str(shot.get('take_id') or 'isolated_'+str(sid)))
            if len(direct)<2:
                raise RuntimeError('only one evidenced moment')
            # At least one long physical recording or several medium recorded
            # takes can serve a narration without inventing new source moments.
            usable=sum(hi-lo for tid,(lo,hi) in bounds.items() if tid in chosen_takes)
            if usable<15:
                raise RuntimeError('short source camera takes')
            report=v28.coverage_report(item,shots)
            quality=(glyphs(bs)>=TARGETS[target], len(bs), len(direct),usable)
            for beat in bs:
                beat['_v35_contextual']=True
                beat['caption']='ภาพประกอบจากต้นฉบับ • '+str(beat.get('caption') or beat['narration'])[:62]
            result['captions']=[b['caption'] for b in bs]
            result['script']=' '.join(b['narration'] for b in bs)
            result['_v35_contextual']={'source':name,'model_verified_shots':len(direct),
                'model_supported_beats':len(bs),'physical_take_seconds':round(usable,2),
                'evidenced_partitions_not_runtime':report.get('evidenced_partition_seconds',0),
                'no_generated_video':True,'no_model_evidence_invented':True,
                'visual_illustration_disclosed':True}
            options.append((quality,name,result))
            diagnostics.append({'source':name,'eligible':True,'verified_shots':len(direct),
                                'narration_beats':len(bs),'take_seconds':round(usable,1)})
        except (RuntimeError,ValueError,KeyError,TypeError) as e:
            diagnostics.append({'source':name,'eligible':False,'reason_type':type(e).__name__})
    if not options:return None,diagnostics
    best=max(options,key=lambda x:x[0]);return best[2],diagnostics


def windows_for(beats,duration,wav):
    import v21_storyflow as v21
    return v21.phrase_windows(beats,duration,wav)


def continuous_cuts(beats,voice_duration,source_duration,shots,wav=None):
    """Try time-forward source edits within proved physical takes; no loops.

    Each selected camera take MUST contain a verified subject/timecode anchor
    for that exact narrated beat. The footage extension cannot cross real cuts.
    """
    bounds=takes(shots,source_duration)
    lookup={str(s.get('id')):s for s in shots if isinstance(s,dict)}
    windows=windows_for(beats,voice_duration,wav)
    if not beats or len(windows)!=len(beats):raise RuntimeError('bad narration windows')
    cursor=0.;out=[]
    for beat,(va,vb) in zip(beats,windows):
        needed=vb-va
        if needed<.2:raise RuntimeError('voice segment too short')
        identifiers=list(dict.fromkeys(str(x) for x in
            [beat.get('shot_id')]+list(beat.get('related_shots') or []) if x is not None))
        candidates=[]
        for sid in identifiers:
            s=lookup.get(sid)
            if not s:continue
            tid=str(s.get('take_id') or 'isolated_'+sid)
            if tid not in bounds:continue
            a,b=bounds[tid]
            anchor_a=float(s['start']); anchor_b=float(s['end'])
            # Prefer starting AT the independently evidenced moment and running
            # forward inside the same actual uncut take. If near the take's end,
            # allow a contextual lead-in while still displaying the anchor.
            start=max(cursor,a,anchor_a)
            if start+needed>b+.0001:
                start=max(cursor,a,anchor_b-needed)
            if (start+needed>b+.0001 or start-anchor_b>max(15.,needed*2.)
                    or start+needed<anchor_a+.2):
                continue
            candidates.append((start,sid,tid))
        if not candidates:raise RuntimeError('no chronologically allocatable camera take')
        start,sid,tid=min(candidates,key=lambda x:(x[0],x[1]))
        remain=needed;source_at=start;voice_at=va
        while remain>.00001:
            take=min(8.,remain)
            if 0<remain-take<.12:take=remain
            out.append({'source_start':round(source_at,5),'duration':round(take,5),
                        'voice_start':round(voice_at,5),'shot_id':sid,
                        'caption':beat['caption'],'text':beat['narration'],
                        '_v35_same_take':tid})
            remain-=take;source_at+=take;voice_at+=take
        cursor=start+needed
    if abs(sum(s['duration'] for s in out)-voice_duration)>.08:
        raise RuntimeError('invalid edit duration')
    if any(y['source_start']+1e-3 < x['source_start']+x['duration']
           for x,y in zip(out,out[1:])):
        raise RuntimeError('source cut would rewind')
    return out


def schedule(beats,voice_duration,source_duration,shots,wav=None):
    """Only if true physical-take continuity fails, transparently repeat verified visuals.

    Never borrow unrelated shots or generate fake evidence; V31 already has a
    proven scheduler that exclusively recuts the *same beat's* approved shots.
    """
    try:
        return continuous_cuts(beats,voice_duration,source_duration,shots,wav)
    except RuntimeError:
        import v31_illustrative as v31
        out=v31.illustrative_cuts(beats,voice_duration,source_duration,shots,wav)
        for c in out:c['_v35_disclosed_visual_repeat']=True
        return out


def install(ns):
    if ns.get('_V35_INSTALLED'):return
    import v11
    import v30_source_first as v30
    before_normalize=v11.normalize_beats
    before_time=v11.time_beats
    before_process=ns['process']

    def normalize(raw,shots,source_duration):
        try:
            return before_normalize(raw,shots,source_duration)
        except RuntimeError as first:
            if not eligible_failure(first):raise
            context=_ACTIVE.get() or v30._JOB.get()
            if not isinstance(context,dict) or not context.get('jid'):raise
            opts=context.get('opts') or {}
            target=int(opts.get('length',60))
            if target not in TARGETS:raise
            folder=Path(ns['WORK'])/str(context['jid'])
            selected,reports=select_grounded(raw,folder,shots,source_duration,target,opts.get('tone',''))
            v11.atom_json(folder/'v35-continuity-diagnostic.json',
                           {'target_seconds':target,'attempts':reports,
                            'result':'contextual_edit' if selected else 'insufficient_evidence'})
            if selected is None:
                raise RuntimeError('ตรวจภาพจากผลวิเคราะห์ที่บันทึกไว้ครบแล้ว แต่ยังมีบทที่ยืนยันภาพจริง '
                     'หรือภาพช่วงต่อเนื่องไม่พอสำหรับคลิปที่เลือก หยุดก่อนใช้โควตา TTS') from first
            ns['notify'](context['jid'],42,
                'พบช่วงถ่ายต่อเนื่องที่เกี่ยวข้อง กำลังเตรียมตัดต่อจากภาพต้นฉบับโดยไม่วนวิเคราะห์เพิ่ม')
            return selected

    def time_beats(beats,duration,source_duration,shots):
        if beats and beats[0].get('_v35_contextual'):
            import v21_storyflow as v21
            ctx=v21._RENDER.get() or {}
            return schedule(beats,duration,source_duration,shots,ctx.get('voice'))
        return before_time(beats,duration,source_duration,shots)

    def process(jid,src_path,link,key,opts):
        t=_ACTIVE.set({'jid':jid,'opts':opts})
        try:
            output=before_process(jid,src_path,link,key,opts)
            with ns['lock']:
                job=ns['jobs'].get(jid)
                if job and job.get('state')=='done':
                    folder=Path(ns['WORK'])/jid
                    analysis=folder/'analysis-v11.json'
                    try:
                        result=json.loads(analysis.read_text('utf8'))
                    except (ValueError,OSError):result={}
                    if isinstance(result,dict) and result.get('_v35_contextual'):
                        job['mode_note']='V35: ภาพประกอบจากวิดีโอต้นฉบับช่วงถ่ายต่อเนื่อง (ไม่มีภาพที่สร้างขึ้นใหม่)'
                        ns['save_job'](jid)
            return output
        finally:_ACTIVE.reset(t)

    v11.normalize_beats=normalize
    v11.time_beats=time_beats
    ns['process']=process
    ns['_V35_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v35_contextual_source_editor=True
    @ns['app'].get('/api/v35/info')
    def info():
        return {'version':VERSION,'sparse_source_context_mode':True,
                'replan_checkpoint_reuse':True,'physical_camera_take_boundaries':True,
                'zero_fabricated_narration_or_visual_matches':True,
                'fallback_repeats_disclosed':True,'target_options':[60,90,120],
                'applies_to_all_narration_modes':True,'may_reject_unsupported_scripts':True}
