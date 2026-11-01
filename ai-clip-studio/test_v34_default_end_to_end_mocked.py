"""Real FFmpeg pipeline smoke test for the exact user's SCRIPT 27% pattern.

Mocked Gemini returns 3/7 evidenced beats in the first attempt, then 14/14
independently matched beats in a single V27 replan for DEFAULT (non-knowledge)
tone. Thai TTS is mocked; the full pipeline actually creates an MP4 and resumes
using cached raw/finished media. This is NOT real-user/Gemini validation.
"""
import json, subprocess, time
from pathlib import Path
import pytest


def ff(*args,timeout=750):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-2500:]

def probe(p):
    x=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,nb_frames,avg_frame_rate','-of','json',str(p)],capture_output=True,text=True,timeout=45)
    assert x.returncode==0,x.stderr
    return json.loads(x.stdout)

@pytest.mark.slow
def test_default_short_mode_can_use_one_cached_source_replan_when_v17_mentions_quota(tmp_path,monkeypatch):
    import app,httpx
    assert app.app.state.v34_pretts_coverage_classification
    jid='34'*16
    root=tmp_path/'jobs';root.mkdir();folder=root/jid;folder.mkdir()
    source=folder/'original.mp4'
    ff('-f','lavfi','-i','testsrc2=size=128x72:rate=12:duration=85',
       '-f','lavfi','-i','sine=frequency=245:sample_rate=24000:duration=85',
       '-c:v','libx264','-threads','1','-preset','ultrafast','-crf','32',
       '-c:a','aac','-b:a','24k','-shortest',source)
    class FakeClient:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*exc):return False
        def delete(self,*a,**kw):pass
    monkeypatch.setattr(httpx,'Client',FakeClient)
    monkeypatch.setattr(app,'upload_gemini',lambda *a:{'name':'files/mock','uri':'files/mock'})
    monkeypatch.setattr(app,'WORK',root)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'statuses')
    app.STATUS_DIR.mkdir()
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued','token':'fake','created':time.time()}
    calls=[]
    def model(shots,count,matched):
        subset=shots[:matched]
        scenes=[{'id':s['id'],'description':'ชายกำลังสาธิตงานช่างภายในอาคารที่มีโต๊ะเครื่องมือ',
                 'tags':['คน','งานช่าง','โต๊ะ']} for s in subset]
        text='ช่างสาธิตการทำงานด้วยเครื่องมือในขั้นตอนนี้'
        beats=[]
        for i in range(count):
            shot=subset[i%len(subset)]
            evidence=[{'id':shot['id'],'score':.91,'evidence':'มองเห็นชายสาธิตใช้งานเครื่องมืออยู่ในห้องอย่างชัดเจน'}] if i<matched else []
            beats.append({'narration':text+f' {i+1}',
                          'caption':'ขั้นตอนจากภาพในต้นฉบับ','shot_id':shot['id'],
                          'visual_keywords':['งานช่าง'], 'visual_matches':evidence})
        return {'title':'ขั้นตอนจากวิดีโอจริง','summary':'สรุปเฉพาะภาพที่ยืนยันได้',
                'scenes':scenes,'beats':beats}
    def mock_api(client,method,url,key,**kwargs):
        assert ':generateContent' in url
        shots=json.loads((folder/'shots-v11.json').read_text('utf8'))
        assert len(shots)>=14, len(shots)
        n=len(calls);calls.append(n)
        data=model(shots,7,3) if n==0 else model(shots,14,14)
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(data,ensure_ascii=False)}]}}]}
    monkeypatch.setattr(app,'get_json',mock_api)
    voices=[]
    def voice(client,script,key,voice,wav):
        voices.append(1)
        ff('-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=60',
           '-ac','1','-c:a','pcm_s16le',wav)
        return 60.0
    monkeypatch.setattr(app,'tts',voice)
    opts={'length':60,'tone':'กระชับ น่าติดตาม เหมาะกับคลิปสั้น',
          'voice':'female','keep_sound':False,'captions':True,'aspect':'9:16','editorial_v21':True}
    app.process(jid,str(source),'','mock-no-real-api-key',opts)
    assert app.jobs[jid]['state']=='done', app.jobs[jid]
    assert calls==[0,1], 'exactly one additional source analysis, no looping'
    assert len(voices)==1
    assert (folder/'analysis-replanned-v27.json').is_file()
    analysis=json.loads((folder/'analysis-v11.json').read_text('utf8'))
    assert analysis['beats'] and len(analysis['beats'])>=8
    m=probe(folder/'result.mp4')
    video=next(x for x in m['streams'] if x['codec_type']=='video')
    assert video['avg_frame_rate']=='30/1'
    assert int(video['nb_frames'])==1800
    assert 59.99<=float(m['format']['duration'])<=60.2
    assert any(x['codec_type']=='audio' for x in m['streams'])
    app.jobs[jid]['state']='error'
    app.process(jid,str(source),'','mock-no-real-api-key',opts)
    assert app.jobs[jid]['state']=='done'
    assert calls==[0,1] and len(voices)==1
