# ThaiVoiceLab v1.1

เว็บไซต์ AI โคลนเสียงภาษาไทย ใช้ ElevenLabs Instant Voice Cloning + Eleven v4 Text-to-Dialogue API. จำเป็นต้องมี API Key และบัญชีที่มีสิทธิ์ใช้การโคลนเสียง/เครดิตเพียงพอ

## ติดตั้ง

`pip install -r voice_lab/requirements.txt`

`uvicorn voice_lab.app:app --host 0.0.0.0 --port 8000`

เปิด `http://localhost:8000`

## Render

Build: `pip install -r voice_lab/requirements.txt`  
Start: `uvicorn voice_lab.app:app --host 0.0.0.0 --port $PORT`  
Health path: `/api/health`

## ความเป็นส่วนตัว

API Key อยู่ในเบราว์เซอร์ (sessionStorage เป็นค่าเริ่มต้น หรือ localStorage ถ้าเลือกให้จำ) และส่งผ่าน HTTPS ไปยังเซิร์ฟเวอร์เพื่อขอเสียงกับ ElevenLabs ไม่มี API Key อยู่ในซอร์สโค้ด ผลลัพธ์ MP3 อยู่ในเบราว์เซอร์และดาวน์โหลดได้ ไฟล์ตัวอย่างจะถูกส่งให้ผู้ให้บริการเพื่อใช้โคลนเสียง เก็บ Voice ID ใน localStorage

สำคัญ: โคลนได้เฉพาะเสียงตนเองหรือเสียงที่ได้รับอนุญาต ห้ามแอบอ้าง/หลอกลวง ผู้ให้บริการอาจเรียกเก็บเครดิต

## API

`POST /api/clone`: form-data name, file, consent; header X-ElevenLabs-Key

`POST /api/speak`: JSON text, voice_id; header X-ElevenLabs-Key; output MP3

`DELETE /api/voices/{voice_id}` ลบเสียงใน ElevenLabs จริง

อ้างอิง: https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert และ https://elevenlabs.io/docs/api-reference/voices/ivc/create
