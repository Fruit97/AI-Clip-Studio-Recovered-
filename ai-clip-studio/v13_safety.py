"""Quota-conservative Gemini requests: never auto-replay failed generation calls.

This is purposely limited to Gemini JSON calls. The job's local checkpoints and key handling
are implemented in the existing V11 app. No API key is written to disk.
"""
from __future__ import annotations
import httpx

VERSION='v13-restored-quota-aware-2026-10-30'

def install(ns):
    if ns.get('_V13_SAFETY_INSTALLED'): return
    ns['_V13_SAFETY_INSTALLED']=True
    prior=ns['get_json']
    def quota_safe_json(client, method, url, key, **kwargs):
        # Never automatically repeat POSTs after an ambiguous read timeout: the request
        # may already have been processed/billed upstream.
        try:
            return prior(client,method,url,key,**kwargs)
        except httpx.TimeoutException as exc:
            raise RuntimeError('Gemini ตอบกลับช้าเกินเวลาที่กำหนด หยุดอัตโนมัติเพื่อป้องกันใช้โควตาซ้ำ กรุณาใช้ปุ่มทำงานต่อเมื่อพร้อม') from exc
        except (httpx.ConnectError,httpx.RemoteProtocolError) as exc:
            raise RuntimeError('เชื่อมต่อ Gemini ไม่สำเร็จ ไม่เรียก API ซ้ำอัตโนมัติ กรุณาตรวจเครือข่ายและโควตาก่อนทำงานต่อ') from exc
        except RuntimeError as exc:
            msg=str(exc)
            if 'Gemini API (429)' in msg:
                raise RuntimeError('Gemini API (429): โควตาของ API Key เต็มหรือเกินอัตราที่อนุญาต หยุดเรียก API แล้ว กรุณารอให้โควตารีเซ็ตหรือตรวจสอบแผนใช้งานที่ Google AI Studio') from exc
            if any(f'Gemini API ({code})' in msg for code in (500,502,503,504)):
                raise RuntimeError(msg + ' (ไม่เรียก API ซ้ำอัตโนมัติเพื่อสงวนโควตา)') from exc
            raise
    ns['get_json']=quota_safe_json
    ns['APP_VERSION']=VERSION
    ns['app'].state.quota_aware=True
    ns['app'].state.retry_503_max_attempts=1
    ns['app'].state.retry_429=False
    ns['app'].state.retry_read_timeout=False
    @ns['app'].get('/api/recovery/info')
    def info():
        return {'version':VERSION,'max_retry_503':1,'retry_429':False,
                'retry_ambiguous_timeout':False,'checkpoints':'local only; lost on free-host restarts',
                'source':'uploaded files only','output':'720x1280 30fps'}
