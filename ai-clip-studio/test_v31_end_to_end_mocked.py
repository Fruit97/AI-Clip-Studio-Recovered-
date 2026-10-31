"""Entire V31 educational fallback through the REAL web app, source/proxy/FFmpeg.

Gemini video analysis and voice are mocked; real source images, real WAV and MP4.
Does not assert the mocked AI's claims are true about the synthetic test video.
"""
import json
import subprocess
import time
from pathlib import Path
import pytest


def ff(*args,timeout=750):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],
          capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-2800:]


def probe(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries',
            'format=duration:stream=codec_type,nb_frames,avg_frame_rate',
            '-of','json',str(path)],capture_output=True,text=True,timeout=45)
    assert p.returncode==0,p.stderr
    return json.loads(p.stdout)


@pytest.mark.slow
def test_60_sec_when_only_three_of_sixteen_beats_have_direct_video_matches(tmp_path,monkeypatch):
    import app,httpx
    root=tmp_path/'jobs';root.mkdir()
    jid='31'*16
    folder=root/jid;folder.mkdir()
    src=folder/'original.mp4'
    ff('-f','lavfi','-i','testsrc2=size=128x72:rate=12:duration=85',
       '-f','lavfi','-i','sine=frequency=245:sample_rate=24000:duration=85',
       '-c:v','libx264','-threads','1','-preset','ultrafast','-crf','32',
       '-c:a','aac','-b:a','24k','-shortest',src)
    class FakeClient:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def delete(self,*a,**kw):pass
    monkeypatch.setattr(httpx,'Client',FakeClient)
    monkeypatch.setattr(app,'upload_gemini',lambda *a:{'name':'files/mock','uri':'files/mock'})
    monkeypatch.setattr(app,'WORK',root)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'statuses')
    app.STATUS_DIR.mkdir()
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued',
                   'token':'fake-token','created':time.time()}
    calls=[]
    def fake_analysis(client,method,url,key,**kwargs):
        assert method=='POST' and ':generateContent' in url
        calls.append('analysis')
        shots=json.loads((folder/'shots-v11.json').read_text('utf-8'))
        assert len(shots)>=15
        evidence=shots[:3]
        scenes=[{'id':s['id'],
              'description':'เสือโคร่งกำลังเดินอยู่กลางป่าต้นไม้สูงในตัวอย่างสมมติ',
              'tags':['เสือโคร่ง','ป่า']} for s in evidence]
        narration=('เสือโคร่งเป็นสัตว์ป่าที่มีพฤติกรรมการหากินและการปรับตัวในธรรมชาติ ')
        beats=[]
        for i in range(16):
            matches=[{'id':evidence[i]['id'],'score':.93,
               'evidence':'ภาพต้นฉบับสมมติแสดงเสือโคร่งกำลังเดินในป่าต้นไม้สูง'}] if i<3 else []
            beats.append({'narration':narration+f'ข้อมูลข้อที่ {i+1} ที่มีแหล่งอ้างอิงรองรับ',
                 'caption':f'เรื่องน่ารู้เกี่ยวกับเสือโคร่ง {i+1}',
                 'visual_keywords':['เสือโคร่ง'],'shot_id':evidence[i%3]['id'],
                 'visual_matches':matches})
        output={'title':'ข้อมูลเสือโคร่งที่น่าสนใจ',
              'summary':'เรื่องเกี่ยวกับสัตว์ป่าและวิธีการดำรงชีวิต',
              'scenes':scenes,'beats':beats}
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(output,ensure_ascii=False)}]},
            'groundingMetadata':{'groundingChunks':[{'web':{'uri':'https://example.org/test-only',
                         'title':'Simulated evidence; not a real source'}}]}}]}
    monkeypatch.setattr(app,'get_json',fake_analysis)
    def tts(client,script,key,voice,wav):
        calls.append('TTS')
        ff('-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=60',
           '-ac','1','-c:a','pcm_s16le',wav)
        return 60.
    monkeypatch.setattr(app,'tts',tts)
    opts={'length':60,'tone':'สาระน่ารู้','voice':'female','keep_sound':False,
          'captions':True,'aspect':'9:16','editorial_v21':True}
    app.process(jid,str(src),'','fake-key-123456789',opts)
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert app.jobs[jid]['v31_illustrative']
    assert calls.count('TTS')==1
    assert calls.count('analysis')<=3
    result=json.loads((folder/'analysis-v11.json').read_text('utf8'))
    assert result['v31_fallback']['visually_verified_anchors']==3
    assert 6<=result['v31_fallback']['accepted_facts']<=16
    output=folder/'result.mp4'
    media=probe(output)
    duration=float(media['format']['duration'])
    assert 60-.01<=duration<60.2
    video=next(x for x in media['streams'] if x['codec_type']=='video')
    assert video['avg_frame_rate']=='30/1'
    assert int(video['nb_frames'])==1800
    assert any(x['codec_type']=='audio' for x in media['streams'])
    planned=json.loads((folder/'timeline-v11.json').read_text('utf8'))
    assert any(x['_v31_repeat_index']>0 for x in planned)
    assert all(x['caption'].startswith('ภาพประกอบ') for x in planned)
    assert (folder/'v21_success.marker').exists()
    # On resume no paid analysis or voice call is allowed.
    app.jobs[jid]['state']='error'
    app.process(jid,str(src),'','fake-key-123456789',opts)
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert calls.count('TTS')==1
    assert calls.count('analysis')<=3
