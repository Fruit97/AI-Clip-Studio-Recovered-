"""V27: re-plan visually supported Thai narration once before spending TTS quota.

A full video may contain enough usable scenes while the first Gemini plan maps
its narration to too few of them. Rather than ignoring evidence or looping frames,
perform ONE additional grounded full-video reanalysis when the V26 preflight
rejects a script. Save successful API response before checking the replacement.
No paid retries are made for TTS, and normal successful jobs use no extra calls.
"""
from __future__ import annotations
import contextvars
import json
from pathlib import Path
import re

VERSION = 'v27-source-first-script-replan-2026-10-31'
_JOB = contextvars.ContextVar('v27_job', default=None)
_REPAIR = contextvars.ContextVar('v27_repair', default=None)
MAX_REPLAN = 1


def is_visual_failure(exc):
    """Never retry unrelated failures such as 429 quota, 503, TTS or invalid JSON."""
    msg = str(exc)
    return (isinstance(exc, RuntimeError) and
            any(k in msg for k in ('ภาพที่ AI', 'ภาพที่ยืนยัน', 'ช่วงภาพ',
                                   'ภาพที่เกี่ยวข้อง', 'ต้นฉบับยาว',
                                   'บทที่ยืนยันภาพ', 'ภาพต้นฉบับ')) and
            not any(k in msg for k in ('Gemini API', 'quota', 'โควตา')))


def brief_context(analysis, reason, target):
    """Constrain the repair model to original observed events, not generic filler."""
    existing = []
    for b in (analysis.get('beats') or [])[:18]:
        if isinstance(b, dict):
            existing.append({'shot_id': str(b.get('shot_id',''))[:20],
                             'narration': str(b.get('narration',''))[:150]})
    return {'target_seconds':int(target),
            'first_plan_failure':str(reason)[:300],
            'previous_title':str(analysis.get('title',''))[:120],
            'previous_beats':existing}


def repair_prompt(base, context):
    if context is None:
        return base
    target=int(context['target_seconds'])
    beats={60:'12-20',90:'17-26',120:'22-32'}[target]
    hints=json.dumps(context,ensure_ascii=False)
    return base + (
        '\nFINAL V27 REPAIR PRIORITY (OVERRIDES EARLIER CONTRADICTORY BEAT COUNTS): '
        'The earlier narration-to-video alignment FAILED on this very same video. '
        'DO NOT paraphrase the failed script and reuse the same unverified timestamps. '
        'You MUST first inspect the entire uploaded video again, identify a diverse '
        'CHRONOLOGICAL set of real, visually relevant shot IDs, and only then write '
        'short complete Thai narration sentences individually grounded to those shots. '
        'Plan source IDs in increasing timeline order, no source interval replay. '
        'Prefer '+beats+' concise informative beats (about 3-6 seconds of natural '
        'Thai speech each) with multiple independently visually approved shots '
        'per beat when relevant. Include source real images, not unrelated B-roll. '
        'If one beat has only a very short 2-second take, make that beat brief and '
        'move on to a different real event, rather than forcing an 8-second line. '
        'For knowledge mode, use a real visible subject as illustrative context '
        'for independently grounded facts; do not pretend unseen details are on screen. '
        'Every visual_matches item must refer to a real candidate ID, score >=0.78 '
        'only when deserved, and explain exactly what can be SEEN. Never add '
        'fictitious evidence, filler sentences, repeated footage, or fake facts. '
        'If the source does not support the required natural runtime, do not '
        'pretend that it does. Previous failed attempt context: '+hints)


def install(ns):
    if ns.get('_V27_INSTALLED'):
        return
    import v11
    import v14_semantic as v14
    original_process = ns['process']
    original_normalize = v11.normalize_beats
    original_prompt = v14.make_prompt

    def prompt(timecodes,length,tone):
        return repair_prompt(original_prompt(timecodes,length,tone),_REPAIR.get())
    v14.make_prompt = prompt

    def process(jid,src_path,link,key,opts):
        token = _JOB.set({'jid':jid,'api_key':key,'opts':opts})
        try:
            return original_process(jid,src_path,link,key,opts)
        finally:
            _JOB.reset(token)

    def normalize(raw,shots,duration):
        try:
            return original_normalize(raw,shots,duration)
        except RuntimeError as first:
            ctx=_JOB.get()
            if not (ctx and is_visual_failure(first)):
                raise
            folder=Path(ns['WORK']) / ctx['jid']
            cached=folder/'analysis-replanned-v27.json'
            repaired=None
            if cached.is_file():
                try:
                    repaired=json.loads(cached.read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    repaired=None
            if repaired is None:
                proxy=folder/'analysis_proxy.mp4'
                if not proxy.is_file():
                    raise RuntimeError('ไม่พบไฟล์วิดีโอสำหรับแก้แผนบท กรุณาอัปโหลดใหม่') from first
                selected=int(ctx['opts'].get('length',60))
                note=brief_context(raw,str(first),selected)
                ns['notify'](ctx['jid'],28,'ภาพที่จับคู่ไม่พอ กำลังวางบทและเลือกฉากใหม่จากวิดีโอจริงอีก 1 รอบก่อนสร้างเสียง')
                import httpx
                token=_REPAIR.set(note)
                try:
                    with httpx.Client(timeout=httpx.Timeout(540,connect=20,read=540,write=540,pool=20)) as client:
                        # This path re-uploads the existing reduced video; no new source upload from user.
                        repaired=v11.analyze_proxy(ns,client,proxy,ctx['api_key'],duration,
                                                  shots,selected,ctx['opts']['tone'])
                    import v11 as v11_io
                    v11_io.atom_json(cached,repaired)
                finally:
                    _REPAIR.reset(token)
            try:
                result=original_normalize(repaired,shots,duration)
            except RuntimeError as second:
                raise RuntimeError(
                    'ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว แต่ยังมีช่วงภาพที่ไม่รองรับ '
                    'เรื่องที่พูดได้เพียงพอสำหรับความยาวขั้นต่ำ 60 วินาที '
                    'ระบบไม่วนภาพหรือทำเสียงพากย์เสียโควตา '
                    'ดูเนื้อหา/ช็อตของต้นฉบับก่อนทดลองอีกครั้ง: '+str(second)[:240]
                ) from second
            result['v27_replanned']={'source':'same_original_video',
                                    'extra_gemini_video_analysis':1,
                                    'cached_source_analysis':True,
                                    'voice_api_calls_before_success':0,
                                    'reused_unrelated_footage':False}
            return result

    ns['process']=process
    v11.normalize_beats=normalize
    ns['_V27_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v27_source_first_replan=True
    ns['app'].state.v27_max_extra_video_analysis=MAX_REPLAN

    @ns['app'].get('/api/v27/info')
    def info():
        return {'version':VERSION,'on_visual_preflight_failure':'one additional full-video analysis',
                'checkpoint':'analysis-replanned-v27.json',
                'extra_requests_on_first_pass_success':0,
                'extra_video_analysis_on_failure_max':MAX_REPLAN,
                'no_unrelated_footage':True,'no_repeated_source_intervals':True,
                'only_validated_source_shots':True,'minimum_output_seconds':60}
