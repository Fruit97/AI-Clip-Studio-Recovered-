"""V34: classify V17 pre-voice SOURCE refusal as a SOURCE error.

The legacy V17 error says "not calling TTS to save quota". V27/V30 incorrectly
filtered it as an actual quota or TTS error, so a 6-minute source video could
stop at SCRIPT 27% without ever attempting its cached source-first replan.

Only opt into the precisely identified pre-voice refusal, never HTTP/API, paid
TTS, FFmpeg, or other failures. Retry the original source only if the previous
V27 attempt has not already been saved. No edit to verified-match thresholds.
"""
from __future__ import annotations
from pathlib import Path

VERSION='v34-distinguish-pre-tts-video-coverage-from-actual-quota-2026-11-01'
PRE_VOICE_SOURCE_PREFIX='ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที ไม่เรียก TTS เพื่อป้องกันเสียโควตา'
REPLAN_EXHAUSTED_PREFIX='ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว'
EXTERNAL_ERRORS=('gemini api (','gemini tts error','quota exceeded','read timeout',
                 'ffmpeg:','http 429','http 503','ไฟล์เสียงพากย์')


def source_refusal(exc):
    if not isinstance(exc, RuntimeError):
        return False
    message=str(exc).strip()
    low=message.casefold()
    return (message.startswith(PRE_VOICE_SOURCE_PREFIX)
            and not any(term in low for term in EXTERNAL_ERRORS))


def replan_attempted(folder):
    return (Path(folder)/'analysis-replanned-v27.json').is_file()


def install(ns):
    if ns.get('_V34_INSTALLED'):
        return
    import v27_replan as v27
    import v30_source_first as v30
    old_v27=v27.is_visual_failure
    old_v30=v30.need_deep_repair

    def v27_classify(exc):
        return source_refusal(exc) or old_v27(exc)

    def v30_classify(exc):
        # V27 already used its source re-analysis. More deep uploads for the
        # same job are not justified when that attempted plan already failed.
        if isinstance(exc,RuntimeError) and str(exc).startswith(REPLAN_EXHAUSTED_PREFIX):
            return False
        context=v30._JOB.get()
        if isinstance(context,dict) and context.get('jid'):
            folder=Path(ns['WORK'])/str(context['jid'])
            if replan_attempted(folder) and (source_refusal(exc) or old_v30(exc)):
                return False
        return source_refusal(exc) or old_v30(exc)

    v27.is_visual_failure=v27_classify
    v30.need_deep_repair=v30_classify
    ns['APP_VERSION']=VERSION
    ns['_V34_INSTALLED']=True
    ns['app'].state.v34_pretts_coverage_classification=True
    @ns['app'].get('/api/v34/info')
    def info():
        return {'version':VERSION,
                'pre_voice_source_refusal_is_not_a_tts_or_quota_error':True,
                'source_only_replan':True,
                'cache_avoids_duplicate_replanning':True,
                'actual_http_tts_and_ffmpeg_errors_remain_fatal':True,
                'no_guarantee_that_source_contains_60s_of_supported_events':True}
