"""Patch the packaged AI Clip Studio service without changing its stored source bundle.

Fix the Gemini YouTube request timeout using the documented background Interactions API.
We keep the same URL submission / job polling / video output interface.
"""
import re
import threading
import time

import httpx

REVISION_HEADERS = {'Api-Revision': '2026-05-20'}
WAIT_SECONDS = 900


def apply_hotfix(ns):
    if ns.get('_YOUTUBE_BACKGROUND_PATCHED'):
        return
    ns['_YOUTUBE_BACKGROUND_PATCHED'] = True
    ns['APP_VERSION'] = 'uploads-background-fix-thai-font-2026-10-29-v5'
    previous_process = ns['process']
    local = threading.local()

    def tracked_process(jid, *args, **kwargs):
        local.jid = jid
        try:
            return previous_process(jid, *args, **kwargs)
        finally:
            if hasattr(local, 'jid'):
                del local.jid

    def background_youtube(client, url, key, length, tone):
        normalized = ns['youtube_video_url'](url)
        body = {
            'model': ns['MODEL'],
            'input': [
                {'type': 'text', 'text': ns['video_prompt'](length, tone)},
                {'type': 'video', 'uri': normalized},
            ],
            'response_format': {'type': 'text', 'mime_type': 'application/json'},
            'generation_config': {'temperature': .3},
            'background': True,
            'store': True,  # required for background processing
        }
        interaction_id = None
        deadline = time.monotonic() + WAIT_SECONDS
        count = 0
        jid = getattr(local, 'jid', None)
        try:
            ns['notify'](jid, 24, 'กำลังเริ่มงานวิเคราะห์ YouTube บน Gemini')
            try:
                response = ns['get_json'](
                    client, 'POST', ns['BASE']+'/interactions', key,
                    headers=REVISION_HEADERS, json=body,
                    timeout=httpx.Timeout(55, connect=15))
            except httpx.TimeoutException as exc:
                raise RuntimeError('เครือข่ายหมดเวลาระหว่างเริ่มงาน Gemini (อาจรับงานไปแล้ว กรุณาตรวจโควตาก่อนลองใหม่)') from exc
            interaction_id = response.get('id')
            if not interaction_id or not re.fullmatch(r'[A-Za-z0-9_-]{3,200}', interaction_id):
                if response.get('status', '').lower() == 'completed':
                    return ns['parse_script'](ns['output_text_from_interaction'](response))
                raise RuntimeError('Gemini ไม่ส่งหมายเลขงานกลับมา')
            while True:
                status = str(response.get('status', '')).lower()
                if status == 'completed':
                    return ns['parse_script'](ns['output_text_from_interaction'](response))
                if status in {'failed', 'cancelled', 'requires_action'}:
                    error = response.get('error') or {}
                    detail = error.get('message', '') if isinstance(error, dict) else str(error)
                    raise RuntimeError('Gemini ไม่สามารถวิเคราะห์วิดีโอนี้ได้: '+str(detail or status)[:380])
                if status not in {'in_progress', 'queued', 'pending'}:
                    raise RuntimeError('Gemini ส่งสถานะงานไม่ถูกต้อง: '+status[:70])
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Gemini ยังประมวลผลไม่เสร็จภายใน 15 นาที กรุณาลองลิงก์วิดีโอที่สั้นลง')
                seconds = int(WAIT_SECONDS-remaining)
                ns['notify'](jid, min(45, 25+seconds//40),
                             f'Gemini กำลังวิเคราะห์ YouTube… {seconds} วินาที (ตรวจผลเป็นระยะ)')
                time.sleep(min(5, remaining))
                try:
                    response = ns['get_json'](
                        client, 'GET', ns['BASE']+'/interactions/'+interaction_id,
                        key, headers=REVISION_HEADERS,
                        timeout=httpx.Timeout(55, connect=15))
                    count = 0
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    count += 1
                    if count > 9:
                        raise RuntimeError('ขาดการเชื่อมต่อกับ Gemini ระหว่างตรวจผลหลายครั้ง') from exc
                    ns['notify'](jid, 29, f'เชื่อมต่อ Gemini ขัดข้องชั่วคราว กำลังลองใหม่ ({count}/9)')
                except RuntimeError as exc:
                    # Retry only transient errors; invalid key, entitlement or
                    # unsupported content errors should not consume more quota.
                    if any(f'Gemini API ({status_code})' in str(exc) for status_code in (429, 500, 502, 503, 504)):
                        count += 1
                        if count > 9:
                            raise
                    else:
                        raise
        finally:
            if interaction_id:
                try:
                    client.delete(ns['BASE']+'/interactions/'+interaction_id,
                                  headers={'x-goog-api-key': key, **REVISION_HEADERS},
                                  timeout=15)
                except Exception:
                    pass

    ns['process'] = tracked_process
    ns['analyze_youtube'] = background_youtube
