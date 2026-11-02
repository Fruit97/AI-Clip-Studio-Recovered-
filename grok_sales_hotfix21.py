"""Grok Sales Web 2.1: decode xAI errors and verify model access."""
import base64,io,zipfile,types,json,os,re,urllib.request,urllib.error
from pathlib import Path
base=Path(__file__).resolve().parent
source=zipfile.ZipFile(io.BytesIO(base64.b64decode((base/'site_bundle.b64').read_text()))).read('server.py')
m=types.ModuleType('old_server');m.__file__=str(base/'old_server.py')
exec(compile(source,'old_server.py','exec'),m.__dict__)
def call(url,key,payload=None):
    body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
    r=urllib.request.Request(url,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'},method='GET' if body is None else 'POST')
    try:
        with urllib.request.urlopen(r,timeout=150) as resp: data=resp.read(5000000)
    except urllib.error.HTTPError as err:
        raw=err.read(4000).decode('utf-8','replace')
        try:
            obj=json.loads(raw)
            v=obj.get('error',obj.get('detail',obj.get('message',''))) if isinstance(obj,dict) else obj
            if isinstance(v,dict): v=v.get('message') or v.get('detail') or v.get('code') or str(v)
            if isinstance(v,list): v='; '.join(str(x.get('msg',x)) if isinstance(x,dict) else str(x) for x in v[:3])
            detail=str(v or '')
        except ValueError: detail=raw
        detail=re.sub(r'(?i)(xai-[A-Za-z0-9_-]{10,}|Bearer\\s+\\S+)','[REDACTED]',' '.join(detail.split())[:480])
        hint={400:'คำขอหรือโมเดลไม่รองรับ',401:'API Key ไม่ถูกต้อง',402:'เครดิต API ไม่เพียงพอ',403:'ไม่มีสิทธิ์ใช้โมเดล',404:'ไม่พบโมเดล',429:'เรียก API ถี่เกินไป'}.get(err.code,'เกิดข้อผิดพลาด')
        raise m.AppError(f'xAI HTTP {err.code}: {detail} — {hint}',502)
    except (urllib.error.URLError,TimeoutError):raise m.AppError('เชื่อมต่อ xAI ไม่สำเร็จ',502)
    try:return json.loads(data)
    except ValueError:raise m.AppError('รูปแบบข้อมูลจาก xAI ไม่ถูกต้อง',502)
m.upstream=call
class Handler(m.Handler):
    server_version='GrokSalesWeb/2.1'
    def do_GET(self):
        if self.path.split('?')[0]=='/api/health':return self.reply(200,{'ok':True,'version':'2.1','server_key':bool(os.getenv('XAI_API_KEY') and os.getenv('APP_PASSWORD'))})
        return super().do_GET()
    def do_POST(self):
        if self.path.split('?')[0]!='/api/diagnose':return super().do_POST()
        try:
            key=m.api_key(self.headers)
            models=[]
            for kind in ('language-models','video-generation-models'):
                result=call('https://api.x.ai/v1/'+kind,key)
                entries=result.get('models',result.get('data',[]))
                models.append([x.get('id','') for x in entries if isinstance(x,dict)])
            self.reply(200,{'ok':True,'text_model':m.TEXT_MODEL,'text_available':m.TEXT_MODEL in models[0],'video_model':m.VIDEO_MODEL,'video_available':m.VIDEO_MODEL in models[1],'available_text_models':models[0][:15]})
        except m.AppError as err:self.reply(err.code,{'error':str(err)})
        except Exception:self.reply(500,{'error':'ตรวจสอบโมเดลไม่สำเร็จ'})
page=base/'static/index.html';js=base/'static/app.js'
if page.exists() and 'id="diagnoseKey"' not in page.read_text():
    page.write_text(page.read_text().replace('<button id="toggleKey"','<button id="diagnoseKey" class="btn outline" type="button">ตรวจสอบ API</button><button id="toggleKey"').replace('<details class="owner">','<div id="diagnoseOut" class="feedback" role="status"></div><details class="owner">').replace('Grok Sales Web · v2.0','Grok Sales Web · v2.1'))
if js.exists() and 'DIAG_PATCH_21' not in js.read_text():
    js.write_text(js.read_text()+'''\n// DIAG_PATCH_21\n$('diagnoseKey').addEventListener('click',async()=>{const b=$('diagnoseKey'),o=$('diagnoseOut');b.disabled=true;o.textContent='กำลังตรวจสอบสิทธิ์โมเดล...';try{const x=await api('/api/diagnose',{});o.textContent='Grok เขียนบท: '+(x.text_available?'✅ รองรับ':'❌ ไม่มีโมเดล '+x.text_model)+' · วิดีโอ: '+(x.video_available?'✅ รองรับ':'❌ ไม่มีโมเดล '+x.video_model)+(x.text_available?'':' · โมเดลที่เข้าถึงได้: '+x.available_text_models.join(', '));}catch(e){o.textContent='❌ '+e.message;}finally{b.disabled=false;}});\n''')
if __name__=='__main__':
    import http.server
    port=int(os.getenv('PORT','8000'))
    print('Grok Sales 2.1 live',port,flush=True)
    http.server.ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
