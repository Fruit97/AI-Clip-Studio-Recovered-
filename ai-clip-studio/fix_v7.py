"""Require real video footage and provide meaningful Gemini upload errors."""
from pathlib import Path
import time
import threading
import httpx


def install(ns):
    if ns.get('_REAL_MEDIA_V7'):
        return
    ns['_REAL_MEDIA_V7'] = True
    ns['APP_VERSION'] = 'v7-real-footage-only-2026-10-30'
    old_download = ns['download_source']
    original_process = ns['process']
    is_youtube = ns['is_youtube_url']
    probe = ns['probe']
    work = threading.local()

    def source_only(url, folder):
        work.last_problem = ''
        try:
            return old_download(url, folder)
        except Exception as first:
            work.last_problem = str(first)[:230]
            if not is_youtube(url):
                raise
            # Second provider client is best-effort, not a promise of access.
            # Do not accept a thumbnail or transcript in place of video frames.
            try:
                from yt_dlp import YoutubeDL
                for item in Path(folder).glob('source.*'):
                    item.unlink(missing_ok=True)
                cfg = {'format': 'bv*[height<=720]+ba/b[height<=720]/best',
                       'outtmpl': str(Path(folder) / 'source.%(ext)s'),
                       'merge_output_format': 'mp4', 'noplaylist': True,
                       'socket_timeout': 25, 'retries': 2, 'fragment_retries': 2,
                       'quiet': True, 'no_warnings': True,
                       'max_filesize': ns['MAX_BYTES'],
                       'extractor_args': {'youtube': {'player_client': ['web_safari','web_embedded']}}}
                with YoutubeDL(cfg) as ydl:
                    ydl.download([url])
                options = [p for p in Path(folder).glob('source.*')
                           if p.suffix.lower() in ('.mp4', '.mkv', '.mov', '.webm') and p.stat().st_size > 1000]
                if not options:
                    raise RuntimeError('ไม่พบภาพวิดีโอที่ดาวน์โหลดสำเร็จ')
                candidate = max(options, key=lambda p: p.stat().st_size)
                if candidate.stat().st_size > ns['MAX_BYTES']:
                    raise RuntimeError('ไฟล์ใหญ่เกินความจุเซิร์ฟเวอร์')
                probe(candidate)
                return candidate
            except Exception as second:
                work.last_problem += ' | ' + str(second)[:180]
                raise RuntimeError('YouTube ปฏิเสธการดึงภาพเคลื่อนไหวต้นฉบับจากเซิร์ฟเวอร์นี้: '
                                   + work.last_problem[:300]) from second

    def never_make_fake_video(*args, **kwargs):
        why = getattr(work, 'last_problem', 'YouTube ไม่อนุญาตให้ดึงไฟล์วิดีโอ')
        raise RuntimeError('ไม่สามารถนำภาพจริงจาก YouTube มาตัดต่อได้: ' + why[:300]
                           + ' เว็บจะไม่สร้างคลิปที่มีแต่ข้อความแทนวิดีโอต้นฉบับ')

    def better_gemini_upload(client, path, key):
        # Retry initialization only; never blindly replay a partially completed upload.
        size = path.stat().st_size
        headers = {'x-goog-api-key': key, 'X-Goog-Upload-Protocol': 'resumable',
                   'X-Goog-Upload-Command': 'start',
                   'X-Goog-Upload-Header-Content-Length': str(size),
                   'X-Goog-Upload-Header-Content-Type': 'video/mp4',
                   'Content-Type': 'application/json'}
        resp = None
        for attempt in range(3):
            try:
                resp = client.post('https://generativelanguage.googleapis.com/upload/v1beta/files',
                    headers=headers, json={'file': {'display_name': 'AI Clip Studio source video'}},
                    timeout=httpx.Timeout(60, connect=20))
                if resp.status_code < 400 or resp.status_code not in (429,500,502,503,504):
                    break
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise RuntimeError('Gemini Files API: เชื่อมต่อ Google ไม่สำเร็จ') from exc
            time.sleep(1+attempt)
        def check(response, stage):
            if response.status_code >= 400:
                try:
                    body = response.json()
                    detail = str((body.get('error') or {}).get('message') or response.text).strip()
                except Exception:
                    detail = (response.text or '').strip()
                raise RuntimeError(f'Gemini Files API {stage} HTTP {response.status_code}: '
                    + (detail[:360] if detail else 'Google ไม่ส่งข้อความข้อผิดพลาด'))
        check(resp, 'start')
        url = resp.headers.get('X-Goog-Upload-URL','')
        from urllib.parse import urlparse
        host = urlparse(url)
        if host.scheme != 'https' or host.hostname != 'generativelanguage.googleapis.com':
            raise RuntimeError('Gemini Files API: Google ไม่ส่ง URL อัปโหลดที่ถูกต้อง')
        try:
            with path.open('rb') as f:
                uploaded = client.post(url, content=f,
                    headers={'Content-Length': str(size), 'X-Goog-Upload-Offset': '0',
                             'X-Goog-Upload-Command': 'upload, finalize'},
                    timeout=httpx.Timeout(900, connect=25, write=900, read=300))
        except httpx.RequestError as exc:
            raise RuntimeError('Gemini Files API: การส่งข้อมูลวิดีโอขัดข้องหรือหมดเวลา') from exc
        check(uploaded, 'upload/finalize')
        try:
            remote = uploaded.json()['file']
            name, uri = remote['name'], remote['uri']
        except (ValueError,KeyError,TypeError) as exc:
            raise RuntimeError('Gemini Files API: ไม่ได้รับข้อมูลไฟล์หลังอัปโหลด') from exc
        if not name.startswith('files/') or not uri.startswith('https://'):
            raise RuntimeError('Gemini Files API: metadata วิดีโอไม่ถูกต้อง')
        for _ in range(180):
            state = str(remote.get('state', 'PROCESSING')).upper()
            if state == 'ACTIVE':
                return remote
            if state == 'FAILED':
                raise RuntimeError('Gemini Files API: แปลงไฟล์วิดีโอไม่สำเร็จ')
            if state not in ('PROCESSING','STATE_UNSPECIFIED'):
                raise RuntimeError('Gemini Files API: สถานะไม่ถูกต้อง ' + state[:40])
            time.sleep(3)
            remote = ns['get_json'](client, 'GET', ns['BASE']+'/'+name, key,
                                    timeout=httpx.Timeout(60,connect=20))
        raise RuntimeError('Gemini Files API: ประมวลผลไฟล์เกิน 9 นาที')

    def strict_process(jid, src_path, link, key, opts):
        # Fetch original frames first, BEFORE Gemini, narration or any fallback.
        if not src_path and is_youtube(link):
            try:
                ns['notify'](jid, 10, 'กำลังตรวจและดาวน์โหลดภาพจริงจาก YouTube')
                original = source_only(link, ns['WORK'] / jid)
            except Exception as exc:
                reason = str(exc).replace(key, '[redacted]') if key else str(exc)
                with ns['lock']:
                    ns['jobs'][jid].update(state='error', step='ดึงภาพวิดีโอต้นฉบับไม่สำเร็จ',
                        error='ไม่สามารถนำภาพจริงจาก YouTube มาตัดต่อได้: '
                              + reason[:480] + ' (ไม่มีการสร้างคลิปข้อความแทน)')
                return
            return original_process(jid, str(original), '', key, opts)
        return original_process(jid, src_path, link, key, opts)

    ns['process'] = strict_process
    ns['download_source'] = source_only
    ns['analyze_youtube'] = never_make_fake_video
    ns['render_graphic_summary'] = never_make_fake_video
    ns['upload_gemini'] = better_gemini_upload
    # Honest, explicit contract in the interface.
    page = ns['ROOT'] / 'site' / 'index.html'
    text = page.read_text('utf-8')
    previous = 'YouTube: วางลิงก์ได้ทันที ระบบลองใช้ภาพต้นฉบับก่อน หาก YouTube บล็อกการดาวน์โหลดจะให้ Gemini วิเคราะห์ลิงก์และสร้างคลิปกราฟิกสรุปแทน — ไม่ต้องโหลดไฟล์ลงเครื่อง'
    updated = 'โหมดภาพจริงเท่านั้น: ใช้ภาพจากวิดีโอต้นฉบับมาตัดต่อ หาก YouTube บล็อกการดึงไฟล์บนเซิร์ฟเวอร์ ระบบจะแจ้งข้อผิดพลาด ไม่สร้างภาพตัวหนังสือแทน และไม่ต้องดาวน์โหลดไฟล์ลงมือถือ'
    if previous in text:
        page.write_text(text.replace(previous,updated),'utf-8')
    ns['app'].state.source_footage_required = True
