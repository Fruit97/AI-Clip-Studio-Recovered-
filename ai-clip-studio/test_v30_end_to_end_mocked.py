"""CI-only full V30 app pipeline: mock Gemini, actual source/proxy/FFmpeg/TTS WAV.

This tests software integration and MP4 properties. It is NOT a live Gemini quality
assessment and cannot prove the user's 412.5-second original has enough usable footage.
"""
import json
import subprocess
import time
from pathlib import Path
import pytest


def ff(*args,timeout=600):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],
                     capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-2200:]


def probe(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries',
                      'format=duration:stream=codec_type,nb_frames,avg_frame_rate',
                      '-of','json',str(path)],capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    return json.loads(p.stdout)


@pytest.fixture(scope='module')
def source_video(tmp_path_factory):
    root=tmp_path_factory.mktemp('v30-source')
    source=root/'original.mp4'
    # 240 seconds from a real, moving test pattern with an ambient audio track.
    ff('-f','lavfi','-i','testsrc2=size=128x72:rate=15:duration=240',
       '-f','lavfi','-i','sine=frequency=275:sample_rate=24000:duration=240',
       '-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','ultrafast',
       '-crf','34','-threads','1','-pix_fmt','yuv420p',
       '-c:a','aac','-b:a','40k','-shortest',source,timeout=600)
    assert abs(float(probe(source)['format']['duration'])-240)<.3
    return source


@pytest.mark.slow
@pytest.mark.parametrize('target,beat_count,tone', [
    (60,16,'สาระน่ารู้'),(90,24,'สารคดีจริงจัง'),(120,33,'สาระน่ารู้')
])
def test_full_pipeline_3_durations_real_mp4(source_video,tmp_path,monkeypatch,target,beat_count,tone):
    import app, httpx, v11
    class DummyClient:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def delete(self,*args,**kwargs):return None
    monkeypatch.setattr(httpx,'Client',DummyClient)
    monkeypatch.setattr(app,'upload_gemini',lambda *args:{'name':'files/offline','uri':'files/offline'})
    jid='%032x'%target
    folder=tmp_path/jid;folder.mkdir()
    original=folder/'original.mp4'
    original.write_bytes(source_video.read_bytes())
    monkeypatch.setattr(app,'WORK',tmp_path)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'_job_status')
    app.STATUS_DIR.mkdir(exist_ok=True)
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued','token':'test-token','created':time.time()}
    calls=[]
    # A long enough, grounded, factual script: each sentence has its own visible
    # original source shot and *does not* reuse source time.
    sample=('ภาพต้นฉบับกำลังแสดงเหตุการณ์นี้ต่อเนื่อง ข้อมูลที่เห็นค่อยเปลี่ยนไปตามเวลา ')
    text=sample[:43]
    assert len(''.join(text.split()))>=38
    def fake_api(client,method,url,key,**kwargs):
        assert method=='POST' and ':generateContent' in url, f'Unexpected paid request {url}'
        calls.append('ANALYSIS')
        shots=json.loads((folder/'shots-v11.json').read_text('utf-8'))
        assert len(shots)>=beat_count
        scenes=[{'id':s['id'],'description':'ภาพทดสอบที่กำลังเคลื่อนไหวจากวิดีโอต้นฉบับ',
                 'tags':['ภาพ','เหตุการณ์']} for s in shots]
        beats=[]
        for i,s in enumerate(shots[:beat_count]):
            line=text+('ลำดับภาพ '+str(i+1))
            beats.append({'narration':line,'caption':'ติดตามเหตุการณ์',
                          'shot_id':s['id'],'visual_keywords':['ภาพ','เหตุการณ์'],
                          'visual_matches':[{'id':s['id'],'score':.96,
                              'evidence':'ภาพทดสอบที่กำลังเคลื่อนไหวในช่วงเวลานี้จริง'}]})
        analysis={'title':'ทดสอบระบบตัดต่อที่มีหลักฐานจากภาพจริง',
                  'summary':'ทดสอบการจัดภาพต่อเนื่องตามเวลา','scenes':scenes,'beats':beats}
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(analysis,ensure_ascii=False)}]},
                   'groundingMetadata':{'groundingChunks':[{'web':{'uri':'https://example.org/video-evidence',
                                                              'title':'Synthetic testing only'}}]}}]}
    monkeypatch.setattr(app,'get_json',fake_api)
    # Bypass Gemini TTS but generate *actual audio* of the requested duration.
    def mocked_tts(client,script,key,voice,out):
        calls.append('TTS')
        ff('-f','lavfi','-i',f'sine=frequency=430:sample_rate=24000:duration={target}',
           '-ac','1','-c:a','pcm_s16le',out)
        return float(target)
    monkeypatch.setattr(app,'tts',mocked_tts)
    options={'length':target,'tone':tone,'voice':'female','keep_sound':True,
             'captions':True,'aspect':'9:16','font_style':'bold','editorial_v21':True}
    app.process(jid,str(original),'','offline-dummy-key-000000',options)
    assert app.jobs[jid]['state']=='done',str(app.jobs[jid])
    assert calls==['ANALYSIS','TTS']
    result=folder/'result.mp4'
    assert result.exists()
    p=probe(result)
    got=float(p['format']['duration'])
    assert got+0.01>=target and got<target+0.3,got
    video=next(s for s in p['streams'] if s['codec_type']=='video')
    assert video['avg_frame_rate']=='30/1'
    assert abs(int(video['nb_frames']) - round(target*30))<=2
    assert any(s['codec_type']=='audio' for s in p['streams'])
    timeline=json.loads((folder/'timeline-v11.json').read_text('utf-8'))
    assert all(b['source_start'] >= a['source_start']+a['duration']-.002 for a,b in zip(timeline,timeline[1:]))
    assert (folder/'captions.srt').exists() and (folder/'cover.jpg').exists()
    if tone=='สาระน่ารู้':
        assert app.jobs[jid]['knowledge_sources']
    app.jobs[jid]['state']='error'
    app.process(jid,str(original),'','offline-dummy-key-000000',options)
    assert app.jobs[jid]['state']=='done'
    assert calls==['ANALYSIS','TTS'],'Resume must use checkpoints without new API calls'
