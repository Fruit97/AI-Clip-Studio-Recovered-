"""ThaiVoiceLab / Thai voice-cloning web (Render deployment)."""
from pathlib import Path
import re
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

app = FastAPI(title="ThaiVoiceLab", docs_url=None, redoc_url=None)
BASE = Path(__file__).resolve().parent
UPSTREAM = "https://api.elevenlabs.io"
AUDIO_MAX = 20 * 1024 * 1024
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
MIME = {".wav":"audio/wav", ".mp3":"audio/mpeg", ".m4a":"audio/mp4", ".ogg":"audio/ogg", ".webm":"audio/webm", ".flac":"audio/flac"}

@app.middleware("http")
async def secure(request, call_next):
    resp = await call_next(request)
    resp.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    })
    return resp

def require_key(raw):
    key = (raw or "").strip()
    if not key or len(key) > 512 or any(ord(c)<32 or ord(c)>126 for c in key):
        raise HTTPException(401, "กรุณาใส่ ElevenLabs API Key")
    return key

def valid_sample(filename, data):
    ext = Path(filename).suffix.lower()
    if ext not in MIME or len(data)<1000: return False
    return {
        ".mp3": lambda: data.startswith(b"ID3") or (len(data)>1 and data[0]==255 and data[1]&224==224),
        ".wav": lambda: data.startswith(b"RIFF") and data[8:12]==b"WAVE",
        ".m4a": lambda: len(data)>12 and data[4:8]==b"ftyp",
        ".ogg": lambda: data.startswith(b"OggS"),
        ".webm": lambda: data.startswith(b"\x1a\x45\xdf\xa3"),
        ".flac": lambda: data.startswith(b"fLaC"),
    }[ext]()

def fail_upstream(r):
    messages = {
        400:"ตัวอย่างเสียงหรือข้อมูลไม่ผ่านเงื่อนไข",
        401:"API Key ไม่ถูกต้อง",
        402:"เครดิตไม่พอ หรือแพ็กเกจไม่รองรับ",
        403:"บัญชีนี้ไม่มีสิทธิ์ใช้ฟังก์ชัน",
        404:"ไม่พบเสียงในบัญชี",
        413:"ไฟล์เสียงมีขนาดใหญ่เกิน",
        422:"ข้อมูลไม่ตรงเงื่อนไข API",
        429:"ใช้งานถี่เกินไป กรุณาลองอีกครั้ง",
    }
    raise HTTPException(429 if r.status_code==429 else 502, messages.get(r.status_code, "บริการ AI ไม่สามารถประมวลผลคำขอได้") + " (ElevenLabs HTTP "+str(r.status_code)+")")

async def eleven_post(path, key, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(150, connect=15), follow_redirects=False) as c:
            r = await c.post(UPSTREAM+path, headers={"xi-api-key":key}, **kwargs)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(504, "เชื่อมต่อ ElevenLabs ไม่สำเร็จ") from exc
    if not r.is_success: fail_upstream(r)
    return r

@app.get("/")
async def home(): return FileResponse(BASE/"index.html")

@app.get("/app.js")
async def js(): return FileResponse(BASE/"app.js", media_type="application/javascript")

@app.get("/api/health")
async def health(): return {"status":"ok","provider":"ElevenLabs","model":"eleven_v4","language":"th"}

@app.post("/api/clone")
async def clone(file:UploadFile=File(...), name:str=Form(...), consent:bool=Form(False), x_elevenlabs_key:str|None=Header(None)):
    key = require_key(x_elevenlabs_key)
    if not consent: raise HTTPException(400, "กรุณายืนยันสิทธิ์ในการใช้เสียง")
    name = name.strip()
    if not 1<=len(name)<=75: raise HTTPException(400, "ชื่อเสียงต้องยาว 1–75 อักขระ")
    sample = await file.read(AUDIO_MAX+1)
    if len(sample)>AUDIO_MAX: raise HTTPException(413, "รองรับเสียงไม่เกิน 20 MB")
    if not valid_sample(file.filename or "", sample): raise HTTPException(400, "รูปแบบไฟล์เสียงไม่ถูกต้อง")
    extension = Path(file.filename or "").suffix.lower()
    r = await eleven_post("/v1/voices/add", key, data={"name":name,"remove_background_noise":"false"}, files=[("files[]",("sample"+extension,sample,MIME[extension]))])
    try:
        payload = r.json()
        voice_id = payload["voice_id"]
        if not isinstance(voice_id,str) or not ID_PATTERN.fullmatch(voice_id): raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "บริการ AI ส่ง Voice ID ไม่ถูกต้อง")
    return {"voice_id":voice_id, "name":name, "requires_verification":bool(payload.get("requires_verification"))}

class SpeechBody(BaseModel):
    voice_id:str = Field(min_length=8,max_length=80)
    text:str = Field(min_length=1,max_length=2000)

@app.post("/api/speak")
async def speak(data:SpeechBody,x_elevenlabs_key:str|None=Header(None)):
    key = require_key(x_elevenlabs_key)
    if not ID_PATTERN.fullmatch(data.voice_id): raise HTTPException(400, "Voice ID ไม่ถูกต้อง")
    if not data.text.strip(): raise HTTPException(400, "กรุณาใส่ข้อความ")
    r = await eleven_post("/v1/text-to-dialogue?output_format=mp3_44100_128",key,json={
        "model_id":"eleven_v4","language_code":"th","inputs":[{"voice_id":data.voice_id,"text":data.text}]
    })
    if not (r.content.startswith(b"ID3") or (len(r.content)>1 and r.content[0]==255 and r.content[1]&224==224)):
        raise HTTPException(502, "ไม่ได้รับไฟล์ MP3 ที่ถูกต้อง")
    return Response(r.content,media_type="audio/mpeg",headers={"Content-Disposition":'attachment; filename="thai-voice.mp3"'})

@app.delete("/api/voices/{voice_id}")
async def delete_voice(voice_id:str,x_elevenlabs_key:str|None=Header(None)):
    key = require_key(x_elevenlabs_key)
    if not ID_PATTERN.fullmatch(voice_id): raise HTTPException(400, "Voice ID ไม่ถูกต้อง")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30,connect=10),follow_redirects=False) as c:
            r = await c.delete(UPSTREAM+"/v1/voices/"+voice_id, headers={"xi-api-key":key})
    except (httpx.TimeoutException,httpx.NetworkError) as exc:
        raise HTTPException(504, "เชื่อมต่อ ElevenLabs ไม่สำเร็จ") from exc
    if not r.is_success: fail_upstream(r)
    return {"deleted":True}
