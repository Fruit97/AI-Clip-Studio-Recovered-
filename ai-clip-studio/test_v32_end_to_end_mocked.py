"""Real FFmpeg pipeline with a 412.5s synthetic source (4/5 -> 12/12 matches).

The synthetic test clip and Gemini response are MOCKS, not a test of the user's
private 412.5s clip or live Gemini factual accuracy.
"""
import json, subprocess, time
from pathlib import Path
import pytest


def ff(*args, timeout=720):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],
                     capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-1500:]


@pytest.mark.slow
def test_two_pass_visual_evidence_is_recovered_into_a_real_mp4(tmp_path,monkeypatch):
    import app, httpx
    folder=tmp_path/'jobs';folder.mkdir();jid='32'*16
    work=folder/jid;work.mkdir()
    source=work/'original.mp4'
    ff('-f','lavfi','-i','testsrc2=size=128x72:rate=10:duration=412.5',
       '-f','lavfi','-i','sine=frequency=300:sample_rate=16000:duration=412.5',
       '-c:v','libx264','-threads','1','-preset','ultrafast','-crf','35',
       '-c:a','aac','-b:a','24k','-shortest',source)
    class DummyClient:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def delete(self,*args,**kwargs):return None
    monkeypatch.setattr(httpx,'Client',DummyClient)
    monkeypatch.setattr(app,'upload_gemini',lambda *a:{'name':'files/mock','uri':'files/mock'})
    monkeypatch.setattr(app,'WORK',folder)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'status')
    app.STATUS_DIR.mkdir()
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued','token':'test-token','created':time.time()}
    calls=[]
    def mocked_analysis(client,method,url,key,**kwargs):
        assert method=='POST' and ':generateContent' in url
        calls.append('VIDEO')
        shots=json.loads((work/'shots-v11.json').read_text(encoding='utf8'))
        assert len(shots)>=60
        target=len(calls)
        n=5 if target==1 else 12
        selected=shots[:n]
        scenes=[{'id':s['id'],
            'description':'เสือโคร่งเดินอยู่ในป่าต้นไม้และมีรายละเอียดพฤติกรรมที่สังเกตได้',
            'tags':['เสือโคร่ง','ต้นไม้']} for s in selected]
        base='เสือโคร่งเป็นสัตว์ป่าที่มีพฤติกรรมการปรับตัวในธรรมชาติและมีบทบาทสำคัญต่อระบบนิเวศ '
        beats=[]
        for i,s in enumerate(selected):
            beats.append({'narration':base+'เรื่องที่ '+str(i+1)+' ซึ่งอ้างอิงจากข้อมูลความรู้ที่ตรวจสอบได้',
                'caption':'เรื่องน่ารู้ของเสือโคร่ง','visual_keywords':['เสือโคร่ง'],
                'shot_id':s['id'],'visual_matches':([{
                    'id':s['id'],'score':.92,
                    'evidence':'มองเห็นเสือโคร่งเดินอยู่ในป่าต้นไม้ในวิดีโอต้นฉบับจริง'}]
                    if (target!=1 or i<4) else [])})
        raw={'title':'ความรู้เกี่ยวกับเสือโคร่ง','summary':'เรื่องน่ารู้เกี่ยวกับเสือโคร่ง',
             'scenes':scenes,'beats':beats}
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(raw,ensure_ascii=False)}]},
                'groundingMetadata':{'groundingChunks':[{'web':{
                     'uri':'https://example.org/simulated-citations-only',
                     'title':'Simulated source only'}}]}}]}
    monkeypatch.setattr(app,'get_json',mocked_analysis)
    def mocked_tts(client,script,key,voice,path):
        calls.append('VOICE')
        ff('-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=60',
           '-ac','1','-c:a','pcm_s16le',path)
        return 60.
    monkeypatch.setattr(app,'tts',mocked_tts)
    opts={'length':60,'tone':'สาระน่ารู้','voice':'female','keep_sound':False,
          'captions':True,'aspect':'9:16','editorial_v21':True}
    app.process(jid,str(source),'','test-not-a-real-api-key',opts)
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert calls.count('VOICE')==1
    assert 2<=calls.count('VIDEO')<=3
    result=work/'result.mp4'
    assert result.is_file()
    p=subprocess.run(['ffprobe','-v','error','-show_entries',
                       'format=duration:stream=codec_type,nb_frames,avg_frame_rate',
                       '-of','json',str(result)],capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    data=json.loads(p.stdout)
    assert 59.99<=float(data['format']['duration'])<=60.20
    video=next(v for v in data['streams'] if v['codec_type']=='video')
    assert video['avg_frame_rate']=='30/1'
    assert int(video['nb_frames'])==1800
    assert any(v['codec_type']=='audio' for v in data['streams'])
    assert (work/'captions.srt').is_file() and (work/'cover.jpg').is_file()
    # Resume may not call paid services or re-render a complete result.
    before=list(calls)
    app.jobs[jid]['state']='error'
    app.process(jid,str(source),'','test-not-a-real-api-key',opts)
    assert app.jobs[jid]['state']=='done'
    assert calls==before
