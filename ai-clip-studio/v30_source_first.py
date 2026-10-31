"""V30: coverage-first editorial review, safe single deep replan, small natural voice correction.

No model call is made on a passing job. A failing SOURCE/SCRIPT plan may trigger
at most one additional full-video evidence inventory, cached before validation.
Do not claim visually unobserved facts, replay source time, or insert filler.
"""
from __future__ import annotations
import contextvars
import copy
import json
import math
import re
from pathlib import Path

VERSION = 'v30-coverage-first-video-editor-2026-10-31'
_FOCUS = contextvars.ContextVar('v30_coverage_focus', default=None)
_JOB = contextvars.ContextVar('v30_current_job', default=None)
TARGETS = {60: 600, 90: 900, 120: 1200}
SPEED_CORRECTION_LIMIT = 0.95  # no more than 5% slower than original narration


def characters(analysis):
    return sum(len(re.sub(r'\s+', '', str(b.get('narration') or '')))
               for b in analysis.get('beats', ()) if isinstance(b, dict))


def validate_script(analysis, target):
    """Conservative pre-TTS heuristic, not a promise of exact TTS duration."""
    if target not in TARGETS:
        raise ValueError('เลือกคลิป 60, 90 หรือ 120 วินาทีเท่านั้น')
    count = characters(analysis)
    if count < TARGETS[target]:
        raise RuntimeError(f'บทพูดที่มีหลักฐานภาพเหลือ {count} ตัวอักษร แต่โหมด {target} วินาทีต้องมีเนื้อหาที่รองรับมากกว่านี้ก่อนสร้างเสียง')
    return count


def deep_prompt(base, context):
    """Explicit distinct shot budget, targeted by source time rather than length of script alone."""
    if not context:
        return base
    target = context['length']
    beat_range = {60:'14 to 20', 90:'20 to 29', 120:'27 to 36'}[target]
    return base + (
        '\nFINAL V30 FULL-SOURCE INSPECTION: Earlier grounded plan was too SHORT for the '
        f'{target}-second delivery. Inspect images THROUGHOUT the entire uploaded video. '
        'Produce around ' + beat_range + ' chronological complete Thai narration beats '
        'ONLY where genuinely appropriate source footage exists. For each beat provide '
        'several separate distinct original visual_matches IDs (up to eight), each '
        'with its own independently observed real image detail and honest confidence '
        '0.78-1.0. One spoken beat MAY be cut across multiple distinct related shots. '
        'Find enough non-overlapping supported ORIGINAL video time to illustrate '
        f'{target} seconds without replay, without footage from another subject, '
        'and without stretching speech. Cover different periods of the source '
        'instead of just the beginning. Provide scenes[] descriptions for every ID '
        'used, all tied to real timecode IDs. Facts outside the video need '
        'independent search grounding; only SHOW the subject of such facts, never '
        'claim an unseen mechanism was filmed. Aim for substantive Thai text, '
        f'at least {TARGETS[target]} non-whitespace Thai characters in total '
        'IF and ONLY IF the original footage has enough genuine meaningful content. '
        'Never fabricate supporting images, timestamps, scores, or facts to meet '
        'the count. If insufficient verified material, return only what exists. '
        'The system will reject impossible output without using TTS quota.'
    )


def need_deep_repair(exc):
    text = str(exc).lower()
    return (isinstance(exc, RuntimeError)
            and any(s in text for s in ('ภาพ','บทพูดที่มีหลักฐาน','ช่วงภาพ','ต้นฉบับยาว','ช็อต','ภาพต้นฉบับ'))
            and not any(s in text for s in ('gemini api','quota','โควตา','tts','ffmpeg','429','503')))


def adjust_voice(ns, wav, got, target):
    """Use <=5% pitch-preserving correction ONLY for a near-complete original TTS WAV."""
    got=float(got)
    if not math.isfinite(got) or got<=0:
        raise RuntimeError('ไฟล์เสียงพากย์มีระยะเวลาไม่ถูกต้อง')
    if got >= target:
        return got
    if got < target*SPEED_CORRECTION_LIMIT:
        raise RuntimeError(f'เสียงพากย์จริงยาว {got:.2f} วินาที ซึ่งสั้นกว่าเป้าหมาย {target} วินาทีมากเกินกว่าจะปรับอย่างเป็นธรรมชาติ ไม่ยืดคำพูดหรือใช้ภาพซ้ำ')
    wav = Path(wav)
    tmp = wav.with_name('v30_natural_voice.tmp.wav')
    try:
        tempo=got/target
        ns['ffmpeg_run'](['-i',str(wav),'-af',f'atempo={tempo:.8f}',
                          '-c:a','pcm_s16le','-ac','1',str(tmp)],timeout=120)
        observed=float(ns['duration_of'](tmp))
        if observed+0.015 < target:
            raise RuntimeError(f'ผลตรวจเสียงหลังปรับ {observed:.3f} วินาที ยังสั้นกว่าเป้าหมาย {target} วินาที')
        tmp.replace(wav)
        return observed
    finally:
        tmp.unlink(missing_ok=True)


def install(ns):
    if ns.get('_V30_INSTALLED'):
        return
    import v11
    import v14_semantic as v14
    import v27_replan as v27
    import httpx
    before_prompt = v14.make_prompt
    before_normalize = v11.normalize_beats
    before_process = ns['process']
    before_tts = ns['tts']

    def prompt(tc, length, tone):
        return deep_prompt(before_prompt(tc,length,tone),_FOCUS.get())
    v14.make_prompt = prompt

    def normalize(raw,shots,source_duration):
        job=_JOB.get()
        if not job:
            return before_normalize(raw,shots,source_duration)
        target=int(job['opts'].get('length',60))
        if target not in TARGETS:
            raise ValueError('เลือกคลิป 60/90/120 วินาทีเท่านั้น')
        first_error=None
        try:
            result=before_normalize(copy.deepcopy(raw),shots,source_duration)
            validate_script(result,target)
            return result
        except RuntimeError as exc:
            if not need_deep_repair(exc):
                raise
            first_error=exc
        folder=Path(ns['WORK'])/job['jid']
        cached=folder/'analysis-deep-v30.json'
        if cached.is_file():
            try:
                repaired=json.loads(cached.read_text(encoding='utf-8'))
                if not isinstance(repaired,dict) or not isinstance(repaired.get('beats'),list):
                    raise ValueError('invalid deep cache')
            except (ValueError,OSError):
                raise RuntimeError('ไฟล์วิเคราะห์ V30 ที่บันทึกไว้เสียหาย หยุดก่อนเรียก API ซ้ำ') from first_error
        else:
            proxy=folder/'analysis_proxy.mp4'
            if not proxy.is_file():
                raise RuntimeError('ไฟล์ต้นฉบับสำหรับตรวจภาพเชิงลึกสูญหาย กรุณาอัปโหลดใหม่') from first_error
            ns['notify'](job['jid'],29,'ตรวจภาพทุกช่วงของต้นฉบับเชิงลึกอีกหนึ่งรอบก่อนสร้างเสียง')
            token=_FOCUS.set({'length':target})
            try:
                with httpx.Client(timeout=httpx.Timeout(540,connect=20,read=540,write=540,pool=20)) as client:
                    repaired=v11.analyze_proxy(ns,client,proxy,job['key'],source_duration,shots,target,job['opts']['tone'])
                # Save successful API response before performing local checks.
                v11.atom_json(cached,repaired)
            finally:
                _FOCUS.reset(token)
        try:
            result=before_normalize(copy.deepcopy(repaired),shots,source_duration)
            validate_script(result,target)
        except RuntimeError as second:
            record={'target_seconds':target,'source_seconds':round(float(source_duration),2),
                    'status':'verified_source_coverage_insufficient',
                    'first_error_type':type(first_error).__name__,
                    'deep_error_type':type(second).__name__,
                    'supported_script_chars':characters(repaired),
                    'additional_video_analysis_requests_max':1,
                    'note':'Gemini evidence is a model estimate; actual video review remains necessary'}
            v11.atom_json(folder/'v30-capacity-report.json',record)
            raise RuntimeError(
                f'วิเคราะห์ภาพต้นฉบับเชิงลึกแล้ว แต่โหมด {target} วินาทียังมีภาพ/เนื้อหาที่ตรวจยืนยันไม่ครบ '
                f'(บทเชิงลึก {characters(repaired)} ตัวอักษร) ระบบไม่วนภาพหรือใช้เสียงพากย์เสียโควตา '
                'หากคลิปยาวมากแต่ยังไม่ผ่าน กรุณาส่ง MP4 ต้นฉบับเพื่อตรวจภาพจริง'
            ) from second
        result['v30_deep_capacity']={'target_seconds':target,'script_chars':characters(result),
                                     'extra_full_video_calls':1,'source_footage_only':True}
        return result

    def process(jid,src_path,link,key,opts):
        token=_JOB.set({'jid':jid,'key':key,'opts':opts})
        try:
            return before_process(jid,src_path,link,key,opts)
        finally:
            _JOB.reset(token)

    def tts(client,script,key,voice,wav):
        got=before_tts(client,script,key,voice,wav)
        job=_JOB.get()
        if job is None:
            return got
        target=int(job['opts'].get('length',60))
        if target in TARGETS:
            # V11 will check the duration again after TTS. Never make a paid retry.
            return adjust_voice({'ffmpeg_run':v11.ffmpeg_run,'duration_of':v11.duration_of},wav,got,target)
        return got

    ns['process']=process
    ns['tts']=tts
    v11.normalize_beats=normalize
    ns['_V30_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v30_source_coverage_first=True
    ns['app'].state.v30_extra_deep_analysis_max=1
    ns['app'].state.v30_no_extra_tts=True
    ns['app'].state.v30_duration_options=(60,90,120)

    @ns['app'].get('/api/v30/info')
    def info():
        return {'version':VERSION,'duration_options':[60,90,120],
                'full_frame_long_proxy':True,'script_preflight_before_tts':True,
                'supplemental_full_video_analysis_calls_on_failure_max':1,
                'cached_deep_source_analysis':True,'no_extra_tts_requests':True,
                'near_target_voice_correction_limit_percent':5,
                'no_unrelated_or_repeated_footage':True,
                'verified_evidence_not_guaranteed_by_ai':True,
                'limitations':'Successful mock tests cannot establish usable footage in a particular user upload'}
