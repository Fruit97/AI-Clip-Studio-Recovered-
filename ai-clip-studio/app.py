"""AI Clip Studio — functional upload -> Gemini -> TTS -> FFmpeg pipeline.
The user supplies their own Gemini API key; it is kept only in job memory.
"""
import base64
import json
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont
import math

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Body
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
WORK = Path(os.getenv('JOB_DIR', '/tmp/ai-clip-studio'))
WORK.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(os.getenv('MAX_UPLOAD_MB', '1024')) * 1024 * 1024
CHUNK_BYTES = 4 * 1024 * 1024
UPLOAD_TTL = 3600
UPLOAD_DIR = WORK / '_incoming'
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_SECONDS = 1800
APP_VERSION = "v8-upload-only-secure-vault-2026-10-30"
TTL = 3600
CONCURRENCY = 1
BASE = 'https://generativelanguage.googleapis.com/v1beta'
MODEL = os.getenv('VIDEO_MODEL', 'gemini-3.8-flash')
TTS_MODEL = os.getenv('TTS_MODEL', 'gemini-3.8-flash-tts')
app = FastAPI(title='AI Clip Studio', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'site'), name='static')
lock = threading.RLock()
jobs = {}
uploads = {}
STATUS_DIR = WORK / '_job_status'
STATUS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

def _status_path(jid):
    return STATUS_DIR / (jid + '.json')

def save_job(jid):
    """Persist metadata atomically; never store Gemini API keys."""
    item = jobs.get(jid)
    if not item:
        return
    safe = {k:v for k,v in item.items() if k not in ('token', 'api_key')}
    safe['token_sha256'] = hashlib.sha256(item['token'].encode('utf-8')).hexdigest()
    blob = json.dumps(safe, ensure_ascii=False, default=str)
    dest = _status_path(jid)
    tmp = STATUS_DIR / (jid + '.' + secrets.token_hex(6) + '.tmp')
    tmp.write_text(blob, encoding='utf-8')
    os.replace(tmp, dest)

def saved_status(jid, token):
    if not re.fullmatch(r'[0-9a-f]{32}', jid):
        return None
    path = _status_path(jid)
    try:
        item = json.loads(path.read_text('utf-8'))
        supplied = hashlib.sha256(token.encode('utf-8')).hexdigest()
        if not secrets.compare_digest(item.get('token_sha256',''), supplied):
            return None
        if time.time() - float(item.get('created',0)) > TTL:
            return None
        if item.get('state') in ('working','queued'):
            item.update(state='interrupted', progress=0,
                step='งานหยุดเพราะเซิร์ฟเวอร์เริ่มทำงานใหม่',
                error='เซิร์ฟเวอร์รีสตาร์ตระหว่างทำงานและไม่สามารถกู้การประมวลผลเดิมได้ กรุณาอัปโหลดไฟล์อีกครั้ง')
        return item
    except (OSError, ValueError, TypeError):
        return None

executor = ThreadPoolExecutor(max_workers=CONCURRENCY)


def run(cmd, timeout=240):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        msg = p.stderr.decode('utf-8', 'replace')[-1800:]
        raise RuntimeError('FFmpeg: ' + msg)
    return p.stdout.decode('utf-8', 'replace')


def probe(path):
    raw = run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], 25)
    data = json.loads(raw)
    duration = float(data['format'].get('duration', 0))
    video = any(s.get('codec_type') == 'video' for s in data.get('streams', []))
    audio = any(s.get('codec_type') == 'audio' for s in data.get('streams', []))
    if not video or not 0.4 < duration <= MAX_SECONDS:
        raise ValueError('ไฟล์ต้องมีภาพวิดีโอ และมีความยาว 1 วินาที ถึง 30 นาที')
    return duration, audio


def notify(jid, pct, label):
    with lock:
        if jid in jobs:
            jobs[jid]['progress'] = pct
            jobs[jid]['step'] = label
            save_job(jid)


def get_json(client, method, url, key, **kwargs):
    response = client.request(method, url, headers={'x-goog-api-key': key, **kwargs.pop('headers', {})}, **kwargs)
    if response.status_code >= 400:
        try:
            err = response.json().get('error', {})
            detail = str(err.get('message') or response.text)[:420]
        except Exception:
            detail = response.text[:420]
        raise RuntimeError(f'Gemini API ({response.status_code}): {detail}')
    return response.json()


def upload_gemini(client, path, key):
    size = path.stat().st_size
    r = client.post(f'{BASE}/upload/v1beta/files',
        params={'key': key},
        headers={'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
                 'X-Goog-Upload-Header-Content-Length': str(size),
                 'X-Goog-Upload-Header-Content-Type': 'video/mp4', 'Content-Type': 'application/json'},
        json={'file': {'display_name': 'AI Clip Studio upload'}})
    if r.status_code >= 400:
        raise RuntimeError('Gemini upload: ' + r.text[:400])
    upload_url = r.headers.get('X-Goog-Upload-URL')
    if not upload_url or not upload_url.startswith('https://generativelanguage.googleapis.com/'):
        raise RuntimeError('Gemini ไม่ได้ส่งที่อยู่อัปโหลดกลับมา')
    with path.open('rb') as f:
        r = client.post(upload_url, content=f, headers={
            'Content-Length': str(size), 'X-Goog-Upload-Offset': '0',
            'X-Goog-Upload-Command': 'upload, finalize'})
    if r.status_code >= 400:
        raise RuntimeError('Gemini upload: ' + r.text[:400])
    file = r.json()['file']
    for _ in range(75):
        state = file.get('state', 'ACTIVE')
        if state == 'ACTIVE':
            return file
        if state == 'FAILED':
            raise RuntimeError('Gemini ประมวลผลไฟล์วิดีโอไม่สำเร็จ')
        time.sleep(2)
        file = get_json(client, 'GET', f'{BASE}/{file["name"]}', key)
    raise RuntimeError('หมดเวลารอให้ Gemini ประมวลผลวิดีโอ')


def analyze(client, path, key, duration, length, tone):
    remote = upload_gemini(client, path, key)
    prompt = f'''You are a professional Thai short-video scriptwriter and editor. Analyze the ACTUAL video in detail, no invented details. Return ONLY valid JSON object with keys:
"title": short accurate Thai headline,
"summary": informative Thai 1-3 sentences,
"script": natural, speakable Thai narration WITHOUT stage directions, no markdown; aim for approximately {length} seconds spoken Thai at a normal pace (roughly {round(length*2.5)} Thai spoken words). No claims absent from the video.
"captions": 3 to 10 short Thai caption phrases, each <= 60 characters, in the same order as the script,
"highlights": 3 to 8 objects with "start": seconds and "end": seconds that show key parts of the video. Time must be within 0 to {duration:.1f} seconds; end > start by at least 1s.
Narration mood: {tone}. If content is unclear, say so; do not fabricate facts. Select visual moments across the source. Do not include copyrighted external music.'''
    body = {'contents': [{'parts': [{'text': prompt}, {'fileData': {'mimeType': 'video/mp4', 'fileUri': remote['uri']}}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.3}}
    try:
        data = get_json(client, 'POST', f'{BASE}/models/{MODEL}:generateContent', key, json=body)
        parts = data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
        text = '\n'.join(p.get('text', '') for p in parts)
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
        result = json.loads(text)
        if not isinstance(result.get('script'), str) or len(result['script'].strip()) < 15:
            raise ValueError('AI ไม่ได้ส่งบทพากย์ที่ใช้ได้กลับมา')
        return result
    finally:
        # Remove the temporary Gemini Files API copy when possible.
        try:
            client.delete(f'{BASE}/{remote["name"]}', headers={'x-goog-api-key': key})
        except Exception:
            pass


def youtube_video_url(url):
    """Return a strictly vetted canonical URL, never follow arbitrary user URLs."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or host not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be', 'music.youtube.com'}:
        raise ValueError('โปรดใช้ลิงก์ HTTPS ของ YouTube')
    if host.endswith('youtu.be'):
        candidate = parsed.path.strip('/').split('/')[0]
    elif parsed.path == '/watch':
        candidate = parse_qs(parsed.query).get('v', [''])[0]
    elif parsed.path.startswith(('/shorts/', '/live/', '/embed/')):
        candidate = parsed.path.strip('/').split('/')[1]
    else:
        raise ValueError('ต้องเป็นลิงก์วิดีโอ YouTube ไม่ใช่หน้าเพลย์ลิสต์หรือช่อง')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', candidate):
        raise ValueError('รหัสวิดีโอ YouTube ไม่ถูกต้อง')
    return 'https://www.youtube.com/watch?v=' + candidate


def video_prompt(length, tone, duration=None):
    bound = f'0 to {duration:.1f} seconds' if duration is not None else 'the actual video duration; do not guess timestamps'
    return f"""You are a professional Thai short-video scriptwriter and editor. You MUST actually examine the linked VIDEO, and never make up facts. Return ONLY JSON object with keys:
"title": short accurate Thai headline, "summary": Thai 1-3 sentences,
"script": natural, fluent Thai narration suitable for approx {length} seconds at normal speed; plain text without stage directions,
"captions": 4 to 8 short Thai factually correct headline/phrase strings (<=70 chars), in narrative order,
"highlights": 3 to 8 objects with "start" and "end" in seconds that show key moments; timestamps are within {bound}; end greater than start.
Narration mood: {tone}. Base the summary only on what's shown/heard, no invented details, no copyrighted music."""


def output_text_from_interaction(data):
    # The REST Interactions API uses steps[].content[].text, not candidates[].
    blocks = []
    for step in data.get('steps', []):
        if step.get('type') == 'model_output':
            blocks.extend(part['text'] for part in step.get('content', []) if isinstance(part.get('text'), str))
    if not blocks and isinstance(data.get('output_text'), str):
        blocks = [data['output_text']]
    return ''.join(blocks).strip()


def parse_script(raw):
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    result = json.loads(raw)
    if not isinstance(result, dict) or not isinstance(result.get('script'), str) or len(result['script'].strip()) < 15:
        raise ValueError('Gemini ไม่ได้ส่งบทพากย์ที่ใช้ได้กลับมา')
    result['captions'] = result.get('captions') if isinstance(result.get('captions'), list) else []
    result['highlights'] = result.get('highlights') if isinstance(result.get('highlights'), list) else []
    return result


def analyze_youtube(client, url, key, length, tone):
    normalized = youtube_video_url(url)
    body = {
        'model': MODEL,
        'input': [{'type': 'text', 'text': video_prompt(length, tone)}, {'type': 'video', 'uri': normalized}],
        'response_format': {'type': 'text', 'mime_type': 'application/json'},
        'generation_config': {'temperature': .3},
        'store': False,
    }
    try:
        data = get_json(client, 'POST', f'{BASE}/interactions', key, json=body)
        return parse_script(output_text_from_interaction(data))
    except Exception as exc:
        raise RuntimeError('Gemini ไม่สามารถอ่านลิงก์ YouTube นี้ได้ (ต้องเป็นวิดีโอสาธารณะ และคีย์มีโควตา): ' + str(exc)[:400]) from exc


def thai_font(size, bold=False):
    # Debian stores TLWG under opentype or truetype, depending on package release.
    # Prefer Noto Sans Thai, a clean/minimal font with correct Thai shaping in Pillow/RAQM.
    style = 'Bold' if bold else 'Regular'
    candidates = [
        f'/usr/share/fonts/truetype/noto/NotoSansThai-{style}.ttf',
        f'/usr/share/fonts/opentype/tlwg/Garuda{"-Bold" if bold else ""}.otf',
        f'/usr/share/fonts/truetype/tlwg/Garuda{"-Bold" if bold else ""}.ttf',
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size, layout_engine=ImageFont.Layout.RAQM)
    # Fontconfig locates installed fonts even if the distro changes their directory.
    found = subprocess.run(['fc-match', '-f', '%{file}', f'Noto Sans Thai:style={style}:lang=th'],
                           capture_output=True, text=True, timeout=5)
    font_file = found.stdout.strip()
    if found.returncode == 0 and Path(font_file).is_file():
        return ImageFont.truetype(font_file, size, layout_engine=ImageFont.Layout.RAQM)
    raise RuntimeError('เซิร์ฟเวอร์ไม่มีฟอนต์ภาษาไทย Noto Sans Thai (กรุณาตรวจการติดตั้ง fonts-noto-core)')


def break_lines(draw, text, font, max_width, max_lines=5):
    # Thai has no mandatory spaces between words; glyph-based wrapping works for all scripts.
    import textwrap
    text = str(text or '').replace('\n', ' ').strip()[:210]
    lines, line = [], ''
    for char in text:
        trial = line + char
        if draw.textlength(trial, font=font) > max_width and line:
            lines.append(line)
            line = char
        else:
            line = trial
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1]: lines[-1] = lines[-1][:-1] + '…'
    return lines


def slide_image(title, caption, slide_i, total, aspect, dest, caption_style='minimal'):
    size = (540, 960) if aspect == '9:16' else (960, 540)
    w, h = size
    background = Image.new('RGB', size)
    px = background.load()
    for y in range(h):
        t = y / h
        for x in range(w):
            radial = max(0, 1 - math.hypot((x-w*.83)/(w*.86), (y-h*.28)/(h*.94)))
            px[x,y] = (int(9+12*radial), int(21+34*radial+12*t), int(40+20*radial+12*t))
    d=ImageDraw.Draw(background)
    accent = '#50edbc'
    pad = round(w*.075)
    d.rounded_rectangle((pad, pad, w-pad, h-pad), radius=round(w*.04), outline='#24555d', width=2)
    d.ellipse((w*.47, h*.10, w*1.18, h*.6), outline='#2c636b', width=3)
    d.ellipse((w*.58, h*.17, w*1.07, h*.49), outline='#305a66', width=2)
    d.rounded_rectangle((pad*1.6, h*.14, pad*1.6+w*.30, h*.14+40), radius=18, fill='#17453e')
    d.text((pad*1.6+17,h*.14+7),'AI CLIP STUDIO',fill=accent,font=thai_font(16))
    d.text((pad*1.6, h*.30),f'{slide_i+1:02d}  /  {total:02d}',fill=accent,font=thai_font(24))
    heading = thai_font(33 if w==540 else 32,True)
    normal = thai_font(42 if w==540 else 38, caption_style == 'bold')
    for i,line in enumerate(break_lines(d,title,heading,w-pad*3,2)):
        d.text((pad*1.6,h*.39+i*46),line,fill='#a5f1e1',font=heading,stroke_width=0)
    caplines=break_lines(d,caption,normal,w-pad*3,5)
    for i,line in enumerate(caplines):
        d.text((pad*1.6,h*.52+i*(51 if w==540 else 42)),line,fill='#f4fbff',font=normal)
    d.rounded_rectangle((pad*1.6,h*.86,w-pad*1.6,h*.87),radius=4,fill='#264d52')
    d.rounded_rectangle((pad*1.6,h*.86,pad*1.6+(w-pad*3.2)*(slide_i+1)/total,h*.87),radius=4,fill=accent)
    d.text((pad*1.6,h*.90),'สรุปจากวิดีโอ YouTube • ภาพประกอบสร้างใหม่',fill='#aac5d0',font=thai_font(16))
    background.save(dest,quality=90)


def render_graphic_summary(jid, audio, voice_duration, analysis, opts, folder):
    """Make original graphic slides; never falsely present them as original footage."""
    raw_caps = [str(c).strip() for c in analysis.get('captions', []) if str(c).strip()]
    if not raw_caps:
        raw_caps = [str(analysis.get('summary') or analysis['script'])]
    raw_caps = raw_caps[:8]
    n = len(raw_caps)
    for i, c in enumerate(raw_caps):
        slide_image(str(analysis.get('title', 'สรุปคลิป')), c, i, n, opts['aspect'], folder/f'slide_{i:02}.jpg', opts.get('font_style', 'minimal'))
    # Input demuxer supports variable-duration slides, with no external media download.
    manifest=folder/'slides.txt'
    step=voice_duration/n
    paths=[folder/f'slide_{i:02}.jpg' for i in range(n)]
    manifest.write_text(''.join(f"file '{p.name}'\nduration {step:.4f}\n" for p in paths) + f"file '{paths[-1].name}'\n", encoding='utf-8')
    output=folder/'result.mp4'
    w,h=(540,960) if opts['aspect']=='9:16' else (960,540)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(manifest),'-i',str(audio),
         '-vf',f'scale={w}:{h},fps=24,format=yuv420p','-map','0:v:0','-map','1:a:0',
         '-t',f'{voice_duration:.3f}','-c:v','libx264','-preset','veryfast','-crf','24','-threads','2',
         '-c:a','aac','-b:a','128k','-movflags','+faststart',str(output)]
    notify(jid, 79, 'กำลังเรนเดอร์คลิปสรุปจากลิงก์ YouTube')
    run(cmd, 240)
    shutil.copyfile(paths[0],folder/'cover.jpg')
    if opts['captions']:
        captions_srt(raw_caps, voice_duration, folder/'captions.srt')
    return output


def tts(client, script, key, voice, wav_path):
    voice_name = 'Puck' if voice == 'male' else 'Kore'
    body = {'model': TTS_MODEL,
            'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': script,
                       'annotations': [{'type': 'speech_metadata', 'style': 'Natural friendly Thai narrator, clear pronunciation, measured documentary pace'}]}]}],
            'response_format': {'type': 'audio'},
            'generation_config': {'speech_config': [{'voice': voice_name}]}}
    try:
        data = get_json(client, 'POST', f'{BASE}/interactions', key, json=body)
        audio_parts = [x for step in data.get('steps', []) for x in step.get('content', []) if x.get('type') == 'audio' and x.get('data')]
        # Gemini Interactions can return audio as top-level output_audio.
        audio_item = data.get('output_audio') if isinstance(data.get('output_audio'), dict) else None
        audio_b64 = (audio_item or {}).get('data') or (audio_parts[-1]['data'] if audio_parts else None)
        if not audio_b64:
            raise RuntimeError('โมเดลเสียงไม่ได้ส่งไฟล์เสียง WAV กลับมา โปรดตรวจโควตาและสิทธิ์ TTS ของ API Key')
        raw = base64.b64decode(audio_b64, validate=True)
        if raw.startswith(b'RIFF'):
            wav_path.write_bytes(raw)
        else:
            with wave.open(str(wav_path), 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(raw)
    except Exception as e:
        raise RuntimeError('สร้างเสียงพากย์ไม่สำเร็จ: ' + str(e)) from e
    dur = float(json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(wav_path)], 20))['format']['duration'])
    if not 1 < dur <= 130:
        raise RuntimeError('เสียงพากย์ที่ AI ส่งมามีความยาวผิดปกติ')
    return dur


def captions_srt(captions, seconds, target):
    def t(sec):
        ms = int(max(0, sec)*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    caps = [str(x).strip().replace('\n', ' ')[:100] for x in captions if str(x).strip()][:12]
    if not caps:
        return False
    with target.open('w', encoding='utf-8') as f:
        for i, caption in enumerate(caps):
            # Phrase-level approximate alignment, not word-level forced alignment.
            start, end = seconds * i / len(caps), seconds * (i+1)/len(caps)
            f.write(f'{i+1}\n{t(start)} --> {t(end)}\n{caption}\n\n')
    return True


def make_segments(highlights, source_duration, voice_duration):
    options = []
    for h in (highlights or [])[:10]:
        try:
            s, e = float(h['start']), float(h['end'])
            s = min(max(s, 0), source_duration - 0.5)
            e = min(max(e, s+0.5), source_duration)
            if e - s > 0.6:
                options.append((s, min(e-s, 8)))
        except (ValueError, TypeError, KeyError):
            continue
    if not options:
        span = min(5, max(source_duration/5, 1))
        options = [(max(0, source_duration*i/5), min(span, source_duration - source_duration*i/5)) for i in range(5)]
    built, total, idx = [], 0., 0
    while total < voice_duration + .15 and len(built) < 48:
        start, span = options[idx % len(options)]
        span = min(span, voice_duration + .2 - total)
        if span < .2: break
        built.append((start, span)); total += span; idx += 1
    return built


def render_video(jid, src, audio, source_duration, source_audio, voice_duration, analysis, opts, folder):
    width, height = (540, 960) if opts['aspect'] == '9:16' else (960, 540)
    # Fit with letterboxing; no subject accidentally cropped.
    vf = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps=24,setsar=1'
    cuts = make_segments(analysis.get('highlights', []), source_duration, voice_duration)
    segments = []
    for i, (start, span) in enumerate(cuts):
        dest = folder / f'seg_{i:02d}.mp4'
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.3f}', '-t', f'{span:.3f}', '-i', str(src),
               '-vf', vf, '-map', '0:v:0', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p',
               '-threads', '2']
        if source_audio and opts['keep_sound']:
            cmd += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '64k', '-ar', '24000', '-ac', '1']
        else:
            cmd += ['-an']
        cmd += [str(dest)]
        run(cmd, 120)
        segments.append(dest)
        if i % 2 == 0:
            notify(jid, 65 + int(20*(i+1)/len(cuts)), f'ตัดต่อฉาก {i+1}/{len(cuts)}')
    manifest = folder / 'concat.txt'
    manifest.write_text(''.join("file '" + p.name + "'\n" for p in segments), encoding='utf-8')
    montage = folder / 'montage.mp4'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(manifest),
         '-c', 'copy', str(montage)], 120)
    srt = folder / 'captions.srt'
    has_subs = opts['captions'] and captions_srt(analysis.get('captions', []), voice_duration, srt)
    output = folder / 'result.mp4'
    args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(montage), '-i', str(audio), '-t', f'{voice_duration:.3f}']
    if has_subs:
        # Use the same installed, verified font as PIL cover art for burned-in Thai subtitles.
        weight = 1 if opts.get('font_style') == 'bold' else 0
        size = 21 if opts.get('font_style') == 'bold' else 19
        args += ['-vf', f"subtitles={srt}:force_style='FontName=Noto Sans Thai,Bold={weight},FontSize={size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00141414,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=55'"]
    if source_audio and opts['keep_sound']:
        args += ['-filter_complex', '[0:a]volume=0.16[bg];[bg][1:a]amix=inputs=2:duration=shortest:dropout_transition=0[aout]', '-map', '0:v:0', '-map', '[aout]']
    else:
        args += ['-map', '0:v:0', '-map', '1:a:0']
    args += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '25', '-pix_fmt', 'yuv420p', '-threads', '2',
             '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest', str(output)]
    run(args, 240)
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', '0.5', '-i', str(output), '-frames:v', '1', '-q:v', '4', str(folder/'cover.jpg')], 25)
    return output


ALLOWED_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtu.be', 'tiktok.com', 'facebook.com', 'fb.watch', 'm.facebook.com', 'www.tiktok.com', 'www.facebook.com'}


def download_source(url, folder):
    host = (urlparse(url).hostname or '').lower()
    if urlparse(url).scheme != 'https' or host not in ALLOWED_HOSTS:
        raise ValueError('รองรับเฉพาะลิงก์ HTTPS จาก YouTube, TikTok หรือ Facebook ที่สาธารณะ')
    # Known providers only; platform restrictions may still prevent download.
    from yt_dlp import YoutubeDL
    settings = {'format': 'best[ext=mp4][height<=720]/best[height<=720]/best', 'outtmpl': str(folder/'source.%(ext)s'),
                'merge_output_format': 'mp4', 'noplaylist': True, 'max_filesize': MAX_BYTES,
                'socket_timeout': 20, 'retries': 2, 'quiet': True, 'no_warnings': True,
                'match_filter': lambda info, incomplete: 'วิดีโอยาวเกิน 30 นาที' if info.get('duration', 0) > MAX_SECONDS else None}
    with YoutubeDL(settings) as ydl:
        ydl.download([url])
    matches = [p for p in folder.glob('source.*') if p.suffix.lower() in {'.mp4', '.mkv', '.webm', '.mov'}]
    if not matches:
        raise RuntimeError('ดาวน์โหลดจากแพลตฟอร์มไม่ได้ กรุณาอัปโหลดไฟล์วิดีโอแทน')
    src = max(matches, key=lambda p: p.stat().st_size)
    if src.stat().st_size > MAX_BYTES:
        raise ValueError('ไฟล์จากลิงก์ใหญ่เกินขีดจำกัด')
    if src.suffix != '.mp4':
        target = folder / 'source_converted.mp4'
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(src), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'aac', str(target)], 160)
        src = target
    return src


def process(jid, src_path, link, key, opts):
    folder = WORK / jid
    with lock:
        jobs[jid]['state'] = 'working'
        save_job(jid)
    try:
        notify(jid, 7, 'เตรียมวิดีโอ')
        source = Path(src_path) if src_path else None
        using_youtube_graphics = False
        if not source:
            if is_youtube_url(link):
                try:
                    notify(jid, 10, 'กำลังดึงวิดีโอ YouTube บนเซิร์ฟเวอร์')
                    source = download_source(link, folder)
                except Exception:
                    # YouTube often blocks cloud IPs and requests sign-in. Gemini's
                    # documented YouTube URL input does NOT require yt-dlp at all.
                    using_youtube_graphics = True
                    notify(jid, 23, 'YouTube จำกัดการดึงภาพ กำลังให้ Gemini วิเคราะห์จากลิงก์โดยตรง')
            else:
                source = download_source(link, folder)
        with httpx.Client(timeout=httpx.Timeout(240, connect=25)) as client:
            if using_youtube_graphics:
                analysis = analyze_youtube(client, link, key, opts['length'], opts['tone'])
                source_audio = False
                dur = None
            else:
                dur, source_audio = probe(source)
                if source.suffix.lower() != '.mp4':
                    converted = folder / 'normalized.mp4'
                    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                         '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'ultrafast',
                         '-crf', '28', '-c:a', 'aac', '-movflags', '+faststart', str(converted)], 160)
                    source = converted
                notify(jid, 27, 'กำลังส่งภาพวิดีโอไปให้ Gemini วิเคราะห์')
                analysis = analyze(client, source, key, dur, opts['length'], opts['tone'])
            (folder/'script.txt').write_text(analysis.get('title', '')+'\n\n'+analysis.get('summary', '')+'\n\n'+analysis['script'], encoding='utf-8')
            notify(jid, 51, 'กำลังสร้างเสียงพากย์ภาษาไทย')
            wav = folder/'voice.wav'
            voice_duration = tts(client, analysis['script'], key, opts['voice'], wav)
        notify(jid, 68, 'กำลังตัดต่อ MP4')
        if using_youtube_graphics:
            render_graphic_summary(jid, wav, voice_duration, analysis, opts, folder)
        else:
            render_video(jid, source, wav, dur, source_audio, voice_duration, analysis, opts, folder)
        with lock:
            jobs[jid].update(state='done', progress=100, step='วิดีโอพร้อมดาวน์โหลด',
                             title=str(analysis.get('title', 'สรุปคลิป')), summary=str(analysis.get('summary', '')),
                             script=analysis['script'], seconds=round(voice_duration, 1),
                             mode=('graphics' if using_youtube_graphics else 'original'),
                             mode_note=('YouTube จำกัดการดึงภาพต้นฉบับ คลิปนี้จึงใช้กราฟิกสรุปแทนฉากจากวิดีโอ' if using_youtube_graphics else 'ตัดต่อจากภาพวิดีโอต้นฉบับ'))
    except Exception as e:
        # Preserve the processing step in the user-visible error, without logging keys.
        with lock:
            failed_step = jobs.get(jid, {}).get('step', 'ไม่ทราบขั้นตอน')
            reason = str(e).replace(key, '[redacted]') if key else str(e)
            jobs[jid].update(state='error', step='ประมวลผลไม่สำเร็จ',
                error=f'ขั้นตอน: {failed_step} — {type(e).__name__}: {reason[:620]}')
    finally:
        with lock:
            save_job(jid)
        # Deliberately discard the API key as soon as processing ends.
        key = None
        if folder.exists():
            for entry in folder.iterdir():
                if (entry.name.startswith('seg_') or entry.name.startswith('slide_') or entry.name.startswith('input.')
                        or entry.name.startswith('source.') or entry.name in {'source_converted.mp4','normalized.mp4',
                        'montage.mp4','concat.txt','slides.txt','voice.wav'}):
                    entry.unlink(missing_ok=True)


def is_youtube_url(url):
    host = (urlparse(url).hostname or '').lower()
    return host in {'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtu.be','www.youtu.be'}


def cleanup():
    now = time.time()
    # Abandoned partial uploads are unlinked automatically. Completed jobs remain for one hour.
    for uid, item in list(uploads.items()):
        if now - item['touched'] > UPLOAD_TTL:
            uploads.pop(uid, None)
            shutil.rmtree(UPLOAD_DIR / uid, ignore_errors=True)
    for jid, job in list(jobs.items()):
        if job['state'] in ('done', 'error') and now - job['created'] > TTL:
            shutil.rmtree(WORK / jid, ignore_errors=True)
            _status_path(jid).unlink(missing_ok=True)
            jobs.pop(jid, None)


@app.get('/')
def index():
    return FileResponse(ROOT/'site'/'index.html')


@app.get('/health')
def health():
    return {'ok': True, 'service': 'AI Clip Studio', 'version': APP_VERSION, 'youtube_fallback': False, 'upload_only': True, 'job_status_saved_locally': True, 'ffmpeg': bool(shutil.which('ffmpeg')), 'thai_font': font_available(), 'max_upload_mb': MAX_BYTES//1048576, 'chunk_bytes': CHUNK_BYTES}


@app.post('/api/jobs')
async def create_job(request: Request, video: UploadFile | None = File(None),
                     url: str = Form(''), api_key: str = Form(''),
                     length: int = Form(30), voice: str = Form('female'),
                     aspect: str = Form('9:16'), tone: str = Form('กระชับ'),
                     captions: bool = Form(True), keep_sound: bool = Form(False),
                     rights: bool = Form(False), font_style: str = Form('minimal')):
    url = url.strip()
    if url:
        raise HTTPException(400, 'เวอร์ชันนี้เน้นตัดต่อจากไฟล์จริง กรุณาเลือกอัปโหลด MP4 แทนลิงก์')
    if not rights:
        raise HTTPException(400, 'กรุณายืนยันว่ามีสิทธิ์นำวิดีโอนี้มาประมวลผล')
    if not api_key.strip() or len(api_key) < 12:
        raise HTTPException(400, 'กรุณาใส่ Gemini API Key ที่ใช้งานได้')
    if (not video or not video.filename) == (not url):
        raise HTTPException(400, 'เลือกอัปโหลดไฟล์หรือวางลิงก์อย่างใดอย่างหนึ่ง')
    if length not in (15, 30, 60) or aspect not in ('9:16', '16:9') or voice not in ('male','female') or font_style not in ('minimal','bold'):
        raise HTTPException(400, 'ค่าตั้งค่าไม่ถูกต้อง')
    if len(url) > 1200 or len(tone) > 40:
        raise HTTPException(400, 'ข้อมูลยาวเกินไป')
    if url and (urlparse(url).scheme != 'https' or (urlparse(url).hostname or '').lower() not in ALLOWED_HOSTS):
        raise HTTPException(400, 'ลิงก์ต้องมาจาก YouTube, TikTok หรือ Facebook ผ่าน HTTPS')
    if url and is_youtube_url(url):
        try:
            url = youtube_video_url(url)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    if video and video.filename:
        if Path(video.filename).suffix.lower() not in ('.mp4','.mov','.webm','.mkv'):
            raise HTTPException(400, 'โปรดอัปโหลด MP4, MOV, WEBM หรือ MKV')
    with lock:
        cleanup()
        count = sum(1 for j in jobs.values() if j['state'] in ('queued', 'working'))
        if count >= 2:
            raise HTTPException(429, 'ขณะนี้มีงานเต็ม กรุณาลองใหม่หลังงานก่อนหน้าเสร็จ')
        jid = uuid.uuid4().hex
        token = secrets.token_urlsafe(24)
        jobs[jid] = {'state':'queued','progress':2,'step':'รับงานแล้ว กำลังรอประมวลผล','created':time.time(),'token':token}
        save_job(jid)
    folder = WORK / jid
    folder.mkdir(mode=0o700, exist_ok=True)
    source_path = None
    if video and video.filename:
        source_path = str(folder / ('input'+Path(video.filename).suffix.lower()))
        total = 0
        try:
            with open(source_path, 'wb') as f:
                while chunk := await video.read(1024*1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise HTTPException(413, f'ไฟล์ต้องไม่เกิน {MAX_BYTES//1024//1024} MB')
                    f.write(chunk)
        except Exception:
            with lock: jobs.pop(jid, None)
            shutil.rmtree(folder, ignore_errors=True)
            raise
        finally:
            await video.close()
    opts = {'length':length,'voice':voice,'aspect':aspect,'tone':tone,'captions':captions,'keep_sound':keep_sound, 'font_style':font_style}
    executor.submit(process, jid, source_path, url, api_key.strip(), opts)
    return {'id':jid, 'token':token}




def font_available():
    try:
        font = thai_font(20)
        return bool(font.getbbox('สวัสดี ภาษาไทย'))
    except Exception:
        return False


def new_job_locked():
    cleanup()
    active = sum(1 for record in jobs.values() if record['state'] in ('queued', 'working'))
    if active >= 2:
        raise HTTPException(429, 'มีงานประมวลผลเต็มอยู่ กรุณาลองใหม่หลังงานก่อนหน้าเสร็จ')
    jid = uuid.uuid4().hex
    token = secrets.token_urlsafe(24)
    jobs[jid] = {'state':'queued', 'progress':2, 'step':'รับงานแล้ว กำลังรอประมวลผล', 'created':time.time(), 'token':token}
    save_job(jid)
    return jid, token


@app.post('/api/uploads')
async def begin_upload(payload: dict = Body(...)):
    name = str(payload.get('filename') or '')
    try:
        size = int(payload.get('size'))
    except (ValueError, TypeError):
        raise HTTPException(400, 'ขนาดไฟล์ไม่ถูกต้อง')
    suffix = Path(name).suffix.lower()
    if suffix not in ('.mp4', '.webm', '.mov', '.mkv') or not name or len(name) > 250:
        raise HTTPException(400, 'อัปโหลดได้เฉพาะ MP4, WEBM, MOV, MKV')
    if size < 1 or size > MAX_BYTES:
        raise HTTPException(413, f'ขนาดไฟล์สูงสุด {MAX_BYTES//1048576} MB')
    with lock:
        cleanup()
        if len(uploads) >= 2:
            raise HTTPException(429, 'มีการอัปโหลดอยู่แล้ว 2 งาน กรุณาลองใหม่ภายหลัง')
        # Leave space for FFmpeg temporary segments and final output.
        if shutil.disk_usage(WORK).free < size * 2 + 128*1048576:
            raise HTTPException(507, 'พื้นที่เซิร์ฟเวอร์ไม่พอสำหรับไฟล์นี้และงานตัดต่อ กรุณาลองไฟล์เล็กลง')
        # Prevent unauthenticated clients from filling the free instance disk.
        if sum(item['size'] for item in uploads.values()) + size > MAX_BYTES + CHUNK_BYTES:
            raise HTTPException(429, 'พื้นที่อัปโหลดชั่วคราวไม่เพียงพอ กรุณาทำทีละงาน')
        uid = uuid.uuid4().hex
        token = secrets.token_urlsafe(24)
        uploads[uid] = {'token':token, 'size':size, 'filename':name, 'suffix':suffix,
                        'received':0, 'touched':time.time(), 'busy':False}
    folder = UPLOAD_DIR / uid
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    return {'id':uid, 'token':token, 'chunk_bytes':CHUNK_BYTES, 'max_upload_mb':MAX_BYTES//1048576}


@app.get('/api/uploads/{uid}')
def upload_status(uid: str, token: str):
    with lock:
        item = uploads.get(uid)
        if not item or not secrets.compare_digest(item['token'], token):
            raise HTTPException(404, 'ไม่พบการอัปโหลด')
        item['touched'] = time.time()
        return {'received':item['received'], 'size':item['size'], 'chunk_bytes':CHUNK_BYTES}


@app.put('/api/uploads/{uid}/chunks')
async def upload_chunk(uid: str, request: Request, token: str, offset: int):
    with lock:
        item = uploads.get(uid)
        if not item or not secrets.compare_digest(item['token'], token):
            raise HTTPException(404, 'ไม่พบการอัปโหลด')
        if item['busy']:
            raise HTTPException(409, 'ระบบกำลังบันทึกไฟล์ชิ้นก่อนหน้า')
        if offset != item['received']:
            raise HTTPException(409, f'ตำแหน่งอัปโหลดไม่ตรงกัน (รับแล้ว {item["received"]} ไบต์)')
        item['busy'] = True
        received, size = item['received'], item['size']
    count = 0
    dest = UPLOAD_DIR / uid / 'upload.part'
    try:
        with dest.open('r+b' if dest.exists() else 'wb') as f:
            f.seek(received)
            async for chunk in request.stream():
                count += len(chunk)
                if count > CHUNK_BYTES or received + count > size:
                    f.truncate(received)
                    raise HTTPException(413, 'ข้อมูลชิ้นนี้ใหญ่เกินกำหนด')
                f.write(chunk)
        if count == 0:
            raise HTTPException(400, 'ได้รับไฟล์ว่าง')
        with lock:
            item['received'] += count
            item['touched'] = time.time()
            return {'received': item['received'], 'size':size}
    finally:
        with lock:
            if uid in uploads:
                uploads[uid]['busy'] = False


@app.post('/api/uploads/{uid}/complete')
async def complete_upload(uid: str, token: str, api_key: str = Form(''), length: int = Form(30),
                          voice: str = Form('female'), aspect: str = Form('9:16'),
                          tone: str = Form('กระชับ'), captions: bool = Form(True),
                          keep_sound: bool = Form(False), rights: bool = Form(False),
                          font_style: str = Form('minimal')):
    if not rights:
        raise HTTPException(400, 'กรุณายืนยันสิทธิ์ใช้งานวิดีโอ')
    if len(api_key.strip()) < 12:
        raise HTTPException(400, 'กรุณาใส่ Gemini API Key ที่ใช้งานได้')
    if length not in (15,30,60) or aspect not in ('9:16','16:9') or voice not in ('male','female') or font_style not in ('minimal','bold') or len(tone) > 40:
        raise HTTPException(400, 'การตั้งค่าไม่ถูกต้อง')
    with lock:
        item = uploads.get(uid)
        if not item or not secrets.compare_digest(item['token'], token):
            raise HTTPException(404, 'ไม่พบการอัปโหลด')
        if item['busy'] or item['received'] != item['size']:
            raise HTTPException(409, 'อัปโหลดไฟล์ยังไม่ครบ')
        jid, job_token = new_job_locked()
        folder = WORK / jid
        folder.mkdir(mode=0o700)
        source = folder / ('input'+item['suffix'])
        try:
            (UPLOAD_DIR / uid / 'upload.part').replace(source)
        except Exception:
            jobs.pop(jid, None)
            shutil.rmtree(folder, ignore_errors=True)
            raise
        uploads.pop(uid)
        shutil.rmtree(UPLOAD_DIR / uid, ignore_errors=True)
    opts = {'length':length, 'voice':voice, 'aspect':aspect, 'tone':tone,
            'captions':captions,'keep_sound':keep_sound,'font_style':font_style}
    executor.submit(process, jid, str(source), '', api_key.strip(), opts)
    return {'id':jid, 'token':job_token, 'background':True}


@app.get('/api/jobs/{jid}')
def job_status(jid: str, token: str):
    with lock:
        job = jobs.get(jid)
        if not job or not secrets.compare_digest(job['token'], token):
            saved = saved_status(jid, token)
            if saved:
                return {k:v for k,v in saved.items() if k not in ('token_sha256','created')}
            raise HTTPException(410, 'งานเดิมไม่อยู่บนเซิร์ฟเวอร์แล้ว อาจเกิดจากการพักหรือรีสตาร์ต Render กรุณาอัปโหลดใหม่')
        return {k:v for k,v in job.items() if k not in ('token','created')}


@app.get('/api/jobs/{jid}/files/{kind}')
def job_file(jid: str, kind: str, token: str, preview: bool = False):
    allowed = {'video': ('result.mp4', 'video/mp4'), 'script': ('script.txt','text/plain; charset=utf-8'),
               'captions': ('captions.srt','application/x-subrip'), 'cover': ('cover.jpg', 'image/jpeg')}
    with lock:
        job = jobs.get(jid)
        if not job or not secrets.compare_digest(job['token'], token):
            job = saved_status(jid, token)
        if not job or job['state'] != 'done' or kind not in allowed:
            raise HTTPException(404, 'ไม่พบไฟล์นี้ หรือไฟล์หมดอายุแล้ว')
    filename, mime = allowed[kind]
    path = WORK / jid / filename
    if not path.exists():
        raise HTTPException(404, 'ไม่มีไฟล์นี้')
    if preview and kind == 'video':
        return FileResponse(path, media_type=mime)
    return FileResponse(path, media_type=mime, filename=('AI-Clip-Studio-'+filename) if kind != 'video' else 'AI-Clip-Studio.mp4')

from hotfix import apply_hotfix
apply_hotfix(globals())

from fix_v7 import install
install(globals())

# V8: keep the final server pipeline constrained to locally uploaded footage.
APP_VERSION = 'v8-upload-only-secure-vault-2026-10-30'
V7_process = process

def process(jid, src_path, link, key, opts):
    try:
        if not src_path:
            with lock:
                jobs[jid].update(state='error', error='ต้องอัปโหลดไฟล์วิดีโอต้นฉบับ ไม่รองรับการสร้างภาพจากลิงก์', step='ไม่มีไฟล์ต้นฉบับ')
            return
        return V7_process(jid, src_path, '', key, opts)
    finally:
        with lock:
            save_job(jid)

app.state.upload_only = True

from editorial_v9 import install as install_v9
install_v9(globals())

# Recovery release: semantic edit pipeline, source-related shot reuse, and safe Gemini errors.
from v11 import install as install_v11
install_v11(globals())
from v12 import install as install_v12
install_v12(globals())
from v13_safety import install as install_v13_safety
install_v13_safety(globals())

# V14: per-sentence visual evidence for any narration subject, not keyword templates.
from v14_semantic import install as install_v14
install_v14(globals())

# V15: one-minute editorial delivery with exact 1800-frame verification.
from v15_60seconds import install as install_v15
install_v15(globals())

# V17: prevent oversized voice requests before paid TTS.
from v17_quality import install as install_v17
install_v17(globals())
