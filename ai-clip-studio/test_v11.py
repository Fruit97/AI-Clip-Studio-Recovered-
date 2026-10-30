import json, subprocess
import pytest
import v11

def ff(args):
    r=subprocess.run(args,capture_output=True,text=True,timeout=150)
    assert r.returncode==0, r.stderr[-1500:]

def input_media(tmp_path,width=640,height=360,seconds=6):
    src=tmp_path/'original.mp4'
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i',f'testsrc2=size={width}x{height}:rate=30:duration={seconds}',
        '-f','lavfi','-i',f'sine=frequency=300:sample_rate=44100:duration={seconds}',
        '-c:v','libx264','-preset','ultrafast','-threads','1',
        '-c:a','aac','-b:a','64k','-pix_fmt','yuv420p','-shortest',str(src)])
    return src

def voice_media(tmp_path,seconds=2.5):
    voice=tmp_path/'voice.wav'
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i',f'sine=frequency=800:sample_rate=24000:duration={seconds}',
        '-ac','1',str(voice)])
    return voice

def test_proxy_1080p_and_scene_detection(tmp_path):
    src=input_media(tmp_path,1920,1080,2.1)
    assert v11.make_proxy(src,tmp_path/'proxy.mp4').exists()
    shots=v11.detect_shots(tmp_path/'proxy.mp4',2.1)
    assert shots and shots[-1]['end']<=2.1
    p=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height','-of','json',str(tmp_path/'proxy.mp4')])
    d=json.loads(p)['streams'][0]
    assert d['width']<=640 and d['height']<=360

def test_matching_rejects_unrelated_footage():
    shots=[{'id':'s000','start':0,'end':2},{'id':'s001','start':2,'end':5}]
    a={'scenes':[{'id':'s000','description':'พิธีกรพูดอยู่ในสตูดิโอ','tags':['พิธีกร']},
                 {'id':'s001','description':'น้ำทะเลและคลื่นซัดชายฝั่ง','tags':['ทะเล','คลื่น']}],
       'beats':[{'narration':'น้ำทะเลหนุนสูงขึ้น','caption':'น้ำทะเลหนุนสูง','shot_id':'s000','visual_keywords':['ทะเล','คลื่น']}]}
    result=v11.normalize_beats(a,shots,5)
    assert result['beats'][0]['shot_id']=='s001'
    with pytest.raises(RuntimeError, match='ต้นฉบับมีภาพ'):
        v11.time_beats(result['beats'],6,5,shots)

def test_chunked_render_caption_audio_and_resume(tmp_path):
    src=input_media(tmp_path,640,360,5)
    voice=voice_media(tmp_path,2.5)
    shots=[{'id':'s000','start':0,'end':5}]
    beats=[{'shot_id':'s000','source_start':0,'source_end':5,'narration':'ทดสอบเสียง','caption':'ระดับน้ำทะเลสูงขึ้น'}]
    events=[]
    ns={'notify':lambda jid,p,s:events.append((p,s))}
    opts={'keep_sound':True}
    output=v11.render_timeline(ns,'test-job',src,voice,tmp_path,beats,5,True,2.5,opts,shots)
    assert output.exists() and v11.media_ok(output)
    d=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
      'stream=codec_type,width,height,avg_frame_rate','-of','json',str(output)]))
    pic=next(s for s in d['streams'] if s['codec_type']=='video')
    assert (pic['width'],pic['height'],pic['avg_frame_rate'])==(720,1280,'30/1')
    assert any(s['codec_type']=='audio' for s in d['streams'])
    first=tmp_path/'v11_part_000.mp4';modified=first.stat().st_mtime_ns
    assert output==v11.render_timeline(ns,'test-job',src,voice,tmp_path,beats,5,True,2.5,opts,shots)
    assert first.stat().st_mtime_ns==modified
    assert (tmp_path/'captions.srt').exists()

def test_full_mocked_pipeline_and_restart_checkpoint(tmp_path,monkeypatch):
    import app
    from pathlib import Path
    from threading import RLock
    src=input_media(tmp_path,640,360,6)
    folder=tmp_path/'00000000000000000000000000000001'
    folder.mkdir()
    target=folder/'input.mp4'
    target.write_bytes(src.read_bytes())
    assert target.is_file()
    mock_voice=voice_media(tmp_path,2.0)
    # Never use a real key or contact Google for this integration test.
    monkeypatch.setattr(app,'WORK',tmp_path)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'_job_status')
    app.STATUS_DIR.mkdir(exist_ok=True)
    app.jobs.clear()
    jid=folder.name;token='test-token'
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued','token':token,'created':__import__('time').time()}
    def fake_analysis(ns,client,proxy,key,duration,shots,length,tone):
        return {'title':'เรื่องราวทดลอง','summary':'ข้อมูลจากภาพทดลอง',
            'scenes':[{'id':shots[0]['id'],'description':'ภาพจริง','tags':['ภาพจริง']}],
            'beats':[{'narration':'ภาพจริงที่กำลังแสดง','caption':'ภาพจริงของต้นฉบับ',
                      'shot_id':shots[0]['id'],'visual_keywords':['ภาพจริง']}]}
    monkeypatch.setattr(v11,'analyze_proxy',fake_analysis)
    monkeypatch.setattr(app,'tts',lambda client,script,key,voice,wav: (wav.write_bytes(mock_voice.read_bytes()), 2.0)[1])
    v11.install(app.__dict__)
    app.process(jid,str(target),'','test_fake_key_12345678',
                {'length':15,'tone':'สารคดี','voice':'female','keep_sound':True,'captions':True,'aspect':'9:16'})
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert v11.media_ok(folder/'result.mp4')
    assert (folder/'shots-v11.json').exists()
    assert (folder/'analysis-v11.json').exists()
    assert (folder/'voice.wav').exists()
    assert (folder/'args-v11.json').exists()
    assert (folder/'v11_part_000.mp4').exists()
    old_time=(folder/'v11_part_000.mp4').stat().st_mtime_ns
    app.jobs[jid]['state']='error'
    app.process(jid,str(target),'','test_fake_key_12345678',
                {'length':15,'tone':'สารคดี','voice':'female','keep_sound':True,'captions':True,'aspect':'9:16'})
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert (folder/'v11_part_000.mp4').stat().st_mtime_ns==old_time
