"""V23: bounded recovery from confirmed Gemini 503 at SCRIPT only.

No retries for 429 (quota), ambiguous timeouts, networking, or TTS. Retains the
V11 checkpoint/resume path and never reuploads a source within retry attempts.
"""
from __future__ import annotations
import contextvars
import time

VERSION = 'v23-script-503-bounded-recovery-2026-10-31'
_CURRENT_JOB = contextvars.ContextVar('v23_current_job', default=None)
_SCRIPT_BASE = 'https://generativelanguage.googleapis.com/v1beta/models/'
_DELAYS = (4.0, 12.0)


def is_script_call(method, url):
    return (str(method).upper() == 'POST' and
            str(url).split('?', 1)[0].startswith(_SCRIPT_BASE) and
            str(url).split('?', 1)[0].endswith(':generateContent'))


def call_with_bounded_retry(previous, client, method, url, key, kwargs,
                            *, sleep=time.sleep, delays=_DELAYS, notify_retry=None):
    """Retry only explicit HTTP 503 replies for video/script generateContent.

    An HTTP response with 503 is certain; read timeouts are *not* safe to replay
    automatically because Google might have completed a chargeable request.
    """
    retries = 0
    while True:
        try:
            return previous(client, method, url, key, **kwargs)
        except RuntimeError as exc:
            if not is_script_call(method, url) or 'Gemini API (503)' not in str(exc):
                raise
            if retries >= len(delays):
                raise RuntimeError(
                    'Gemini API (503): ระบบ Google ยังคงมีคำขอมากเกินไป '
                    f'(ลองเรียกสร้างบททั้งหมด {retries + 1} ครั้งแล้ว) '
                    'ระบบเก็บไฟล์ต้นฉบับและขั้นตอนที่เสร็จแล้วไว้ในงานนี้ '
                    'กรุณากด "ทำงานต่อจากจุดที่สำเร็จแล้ว" เมื่อบริการพร้อม '
                    'ไม่จำเป็นต้องอัปโหลดไฟล์ใหม่ถ้างานยังอยู่บนเซิร์ฟเวอร์'
                ) from exc
            delay = float(delays[retries])
            retries += 1
            if notify_retry is not None:
                try:
                    notify_retry(retries, len(delays), delay)
                except Exception:
                    pass
            sleep(delay)


def install(ns):
    if ns.get('_V23_RETRY_INSTALLED'):
        return
    previous_json = ns['get_json']
    previous_process = ns['process']

    def wrapped_json(client, method, url, key, **kwargs):
        def notify_retry(attempt, total, delay):
            jid = _CURRENT_JOB.get()
            if jid is not None:
                ns['notify'](jid, 28,
                    f'Gemini ตอบ 503 (ระบบหนาแน่น) รอ {delay:g} วินาที ก่อนลองใหม่ {attempt}/{total}')
        return call_with_bounded_retry(
            previous_json, client, method, url, key, kwargs,
            notify_retry=notify_retry)

    def process(jid, src_path, link, key, opts):
        token = _CURRENT_JOB.set(jid)
        try:
            return previous_process(jid, src_path, link, key, opts)
        finally:
            _CURRENT_JOB.reset(token)

    ns['get_json'] = wrapped_json
    ns['process'] = process
    ns['_V23_RETRY_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.retry_503_max_attempts = 1 + len(_DELAYS)
    ns['app'].state.retry_503_script_only = True

    @ns['app'].get('/api/v23/info')
    def info():
        return {
            'version': VERSION,
            'retry_only_http_503_script': True,
            'max_script_attempts': 1 + len(_DELAYS),
            'backoff_seconds': list(_DELAYS),
            'retry_429': False,
            'retry_tts': False,
            'retry_ambiguous_read_timeout': False,
            'manual_checkpoint_resume': True,
            'additional_gemini_calls_on_success': 0,
        }
