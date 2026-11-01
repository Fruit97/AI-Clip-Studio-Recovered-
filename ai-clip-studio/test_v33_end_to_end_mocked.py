"""Full app + real synthetic MP4 when Gemini cached outputs separately carry
5/14 and 3/5 visually matched beats. Gemini and Thai voice mocked; all actual
source extraction, timeline and 30-FPS output are real FFmpeg operations.
"""
import json,subprocess,time
from pathlib import Path
import pytest


def ff(*args,timeout=750):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',*map(str,args)],
        capture_output=True,text=True,timeout=timeout)
    assert p.returncode==0,p.stderr[-2000:]


def probe(p):
    x=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,nb_frames,avg_frame_rate','-of','json',str(p)],
          capture_output=True,text=True,timeout=40)
    assert x.returncode==0,x.stderr
    return json.loads(x.stdout)


@pytest.mark.slow
def test_real_mp4_when_both_model_passes_have_too_few_beats_separately(tmp_path,monkeypatch):
    import app,httpx
    jid='33'*16
    root=tmp_path/'jobs';root.mkdir()
    folder=root/jid;folder.mkdir()
    source=folder/'original.mp4'
    ff('-f','lavfi','-i','testsrc2=size=128x72:rate=12:duration=85',
       '-f','lavfi','-i','sine=frequency=245:sample_rate=24000:duration=85',
       '-c:v','libx264','-threads','1','-preset','ultrafast','-crf','32',
       '-c:a','aac','-b:a','24k','-shortest',source)
    class FakeClient:
        def __init__(self,*args,**kw):pass
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
    def facts(shots,passes):
        # Distinct facts are supported by independent model citations.
        # Unmatched proposed beats talk about a different unseen subject;
        # they MUST be excluded, not silently attached to tiger footage.
        count,matched,offset=passes
        anchors=shots[offset:offset+matched]
        scenes=[{'id':s['id'],'description':'เสือโคร่งกำลังเดินอยู่กลางป่าในวิดีโอต้นฉบับ',
                 'tags':['เสือโคร่ง','ป่า']} for s in anchors]
        beats=[]
        for i in range(count):
            is_match=i<matched
            shot=anchors[i%len(anchors)]
            phrase=('เสือโคร่งเป็นสัตว์ป่าที่สำคัญต่อระบบนิเวศ และปรับตัวอยู่ในป่าตามสภาพแวดล้อม '
                    +f'ข้อมูลหัวข้อ {offset}-{i} มีแหล่งอ้างอิง')
            evidence=[{'id':shot['id'],'score':.95,'evidence':'มองเห็นเสือโคร่งจริงกำลังเดินอยู่ในป่าต้นไม้สูง'}] if is_match else []
            beats.append({'narration':phrase,'caption':'ข้อมูลเกี่ยวกับเสือโคร่ง',
                          'shot_id':shot['id'],'visual_keywords':['เสือโคร่ง' if is_match else 'ภูเขาน้ำแข็ง'],
                          'visual_matches':evidence})
        return {'title':'ความรู้เสือโคร่ง','summary':'อธิบายธรรมชาติของสัตว์ป่า',
                'scenes':scenes,'beats':beats}
    def mock_api(client,method,url,key,**kwargs):
        assert ':generateContent' in url
        shots=json.loads((folder/'shots-v11.json').read_text('utf8'))
        assert len(shots)>=15
        idx=len(calls)
        calls.append('analysis')
        result=facts(shots,(14,5,0) if idx==0 else (5,3,5))
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(result,ensure_ascii=False)}]},
           'groundingMetadata':{'groundingChunks':[{'web':{'uri':f'https://example.org/mock{idx}',
                             'title':'Mock grounding only'}}]}}]}
    monkeypatch.setattr(app,'get_json',mock_api)
    tts_calls=[]
    def voice(client,script,key,voice,wav):
        tts_calls.append(1)
        ff('-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=60',
           '-ac','1','-c:a','pcm_s16le',wav)
        return 60.
    monkeypatch.setattr(app,'tts',voice)
    opts={'length':60,'tone':'สาระน่ารู้','voice':'female','keep_sound':False,
          'captions':True,'aspect':'9:16','editorial_v21':True}
    app.process(jid,str(source),'','fake-key-123456789',opts)
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert 2<=len(calls)<=3
    assert len(tts_calls)==1
    a=json.loads((folder/'analysis-v11.json').read_text('utf8'))
    assert a.get('v33_recovery',{}).get('selected_grounded_sources',0)>=2
    assert a['v33_recovery']['distinct_direct_shots']==8
    assert len(a['knowledge_sources'])>=2
    m=probe(folder/'result.mp4')
    v=next(x for x in m['streams'] if x['codec_type']=='video')
    assert v['avg_frame_rate']=='30/1'
    assert int(v['nb_frames'])==1800
    assert 59.99<=float(m['format']['duration'])<60.2
    assert any(x['codec_type']=='audio' for x in m['streams'])
    assert (folder/'v33-coverage.json').is_file()
    app.jobs[jid]['state']='error'
    app.process(jid,str(source),'','fake-key-123456789',opts)
    assert app.jobs[jid]['state']=='done',app.jobs[jid]
    assert len(tts_calls)==1
