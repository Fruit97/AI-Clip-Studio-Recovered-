"""Full offline pipeline with mock Gemini responses and real FFmpeg rendering.
No live API calls or user API key required.
"""
import base64, json, subprocess, time
from pathlib import Path
import pytest

def ff(args,timeout=180):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-1900:]

@pytest.mark.slow
def test_full_pipeline_60_seconds_mock_gemini_real_ffmpeg(tmp_path,monkeypatch):
    import app,httpx,v11
    source=tmp_path/'source.mp4';voice=tmp_path/'synthetic_tts.wav'
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','color=c=#356988:size=192x108:rate=30:duration=65',
        '-f','lavfi','-i','sine=frequency=250:sample_rate=24000:duration=65',
        '-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','48k','-shortest',str(source)])
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','sine=frequency=460:sample_rate=24000:duration=78.7',
        '-ac','1',str(voice)])
    mock_audio=base64.b64encode(voice.read_bytes()).decode('ascii')
    class DummyClient:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self):return self
        def __exit__(self,*args):return None
        def delete(self,*args,**kwargs):return None
    monkeypatch.setattr(httpx,'Client',DummyClient)
    monkeypatch.setattr(app,'upload_gemini',lambda *_:{'name':'files/fake','uri':'files/fake'})
    calls=[]
    folder=tmp_path/'dddddddddddddddddddddddddddddddd';folder.mkdir()
    target=folder/'input.mp4';target.write_bytes(source.read_bytes());jid=folder.name
    monkeypatch.setattr(app,'WORK',tmp_path)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'_job_status')
    app.STATUS_DIR.mkdir(exist_ok=True)
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued','token':'dummy-token','created':time.time()}
    def fake_api(client,method,url,key,**kwargs):
        if 'generateContent' in url:
            calls.append('SCRIPT')
            shots=json.loads((folder/'shots-v11.json').read_text())
            scenes=[{'id':shot['id'],'description':'วิดีโอแสดงภาพสีในต้นฉบับ',
                     'tags':['คลิป','ภาพ']} for shot in shots]
            beats=[{'narration':'กล้องกำลังแสดงภาพสีจากต้นฉบับวิดีโอที่บันทึกต่อเนื่องกันอยู่',
                    'caption':'ภาพต้นฉบับ','shot_id':shot['id'],
                    'visual_matches':[{'id':shot['id'],'score':0.96,
                        'evidence':'เห็นภาพจากวิดีโอต้นฉบับที่จุดเวลาช็อตจริง'}]}
                    for shot in shots[:12]]
            return {'candidates':[{'content':{'parts':[{'text':json.dumps({
                'title':'สาธิต','summary':'ทดสอบออฟไลน์',
                'scenes':scenes,'beats':beats},ensure_ascii=False)}]}}]}
        if '/interactions' in url:
            calls.append('TTS')
            return {'output_audio':{'data':mock_audio}}
        raise AssertionError('Unexpected API: '+url)
    monkeypatch.setattr(app,'get_json',fake_api)
    opts={'length':60,'tone':'สารคดี','voice':'female','keep_sound':True,
          'captions':True,'aspect':'9:16','font_style':'bold'}
    app.process(jid,str(target),'','test_fake_key_123456789',opts)
    assert app.jobs[jid]['state']=='done',str(app.jobs[jid])
    assert calls==['SCRIPT','TTS']
    out=folder/'result.mp4';assert out.exists() and v11.media_ok(out,59.95)
    p=subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=codec_type,nb_frames,avg_frame_rate','-of','json',str(out)])
    data=json.loads(p);v=next(x for x in data['streams'] if x['codec_type']=='video')
    assert v['nb_frames']=='1800' and v['avg_frame_rate']=='30/1'
    assert abs(float(data['format']['duration'])-60)<.05
    assert any(x['codec_type']=='audio' for x in data['streams'])
    assert json.loads((folder/'analysis-v11.json').read_text())['v17_preflight']['additional_gemini_requests']==0
    assert (folder/'captions.srt').exists() and (folder/'cover.jpg').exists()
    app.jobs[jid]['state']='error'
    app.process(jid,str(target),'','test_fake_key_123456789',opts)
    assert app.jobs[jid]['state']=='done'
    assert calls==['SCRIPT','TTS']
