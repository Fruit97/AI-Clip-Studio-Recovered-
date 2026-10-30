import os
import json
import subprocess
from pathlib import Path
import pytest
import v11,v12

class FakeApp:pass

def init():
    ns={'app':FakeApp()}
    ns['app'].state=FakeApp()
    v12.install(ns)
    return ns

def test_semantic_selection_and_short_script():
    init()
    shots=[{'id':'shore','start':0.,'end':2.5},{'id':'presenter','start':2.5,'end':5.5},
           {'id':'waves','start':5.5,'end':7.5}]
    analysis={'scenes':[{'id':'shore','description':'ชายฝั่งและน้ำทะเล','tags':['ทะเล']},
      {'id':'presenter','description':'พิธีกรอยู่ในสตูดิโอ','tags':['พิธีกร']},
      {'id':'waves','description':'คลื่นในทะเลกำลังซัดแรง','tags':['ทะเล','คลื่น']}],
      'beats':[{'narration':'ระดับน้ำทะเลกำลังเพิ่มขึ้นอย่างต่อเนื่องและสร้างผลกระทบกับพื้นที่ชายฝั่ง',
          'caption':'ระดับน้ำทะเลสูงขึ้น','shot_id':'presenter','visual_keywords':['ทะเล']} ]}
    data=v11.normalize_beats(analysis,shots,7.5)
    assert data['beats'][0]['shot_id'] in ('shore','waves')
    assert data['beats'][0]['narration']=='ระดับน้ำทะเลสูงขึ้น'
    assert 'presenter' not in data['beats'][0]['related_shots']
    clips=v11.time_beats(data['beats'],8,7.5,shots)
    assert clips and any(x['reused_related_footage'] for x in clips)
    assert all(x['source_start']<2.5 or x['source_start']>=5.5 for x in clips)
    assert abs(sum(x['duration'] for x in clips)-8)<.08

def test_error_original_case_63_percent_no_more():
    init()
    shots=[{'id':'sea','start':1.,'end':2.2}]
    beats=[{'shot_id':'sea','source_start':1.,'source_end':2.2,'related_shots':['sea'],
            'narration':'น้ำทะเลเพิ่มขึ้นอย่างต่อเนื่อง','caption':'น้ำทะเลเพิ่มขึ้น'}]
    clips=v11.time_beats(beats,13.2,20,shots)
    assert sum(x['duration'] for x in clips)==pytest.approx(13.2,abs=.08)
    assert len(clips)>1 and all(x['source_start']>=1 and x['source_start']+x['duration']<=2.21 for x in clips)

@pytest.mark.slow
def test_renders_original_media_with_repetition(tmp_path):
    init()
    s=tmp_path/'original.mp4';voice=tmp_path/'voice.wav'
    def run(cmd):
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        assert p.returncode==0,p.stderr[-800:]
    run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=2.6','-f','lavfi','-i','sine=frequency=220:sample_rate=24000:duration=2.6','-map','0:v','-map','1:a','-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p','-c:a','aac',str(s)])
    run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=4.2','-ac','1',str(voice)])
    beats=[{'shot_id':'one','source_start':0,'source_end':2.6,'related_shots':['one'],
             'narration':'ภาพต้นฉบับจากเรื่องจริง','caption':'ภาพจริงและเสียงพากย์'}]
    folder=tmp_path/'job';folder.mkdir()
    output=v11.render_timeline({'notify':lambda *args:None},'job',s,voice,folder,beats,2.6,True,4.2,{'keep_sound':True},[{'id':'one','start':0,'end':2.6}])
    assert v11.media_ok(output,4.)
    p=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height,avg_frame_rate','-of','json',str(output)])
    streams=json.loads(p)['streams']
    video=next(x for x in streams if x['codec_type']=='video')
    assert (video['width'],video['height'],video['avg_frame_rate'])==(720,1280,'30/1')
    assert any(x['codec_type']=='audio' for x in streams)
    assert any(x['reused_related_footage'] for x in json.loads((folder/'timeline-v11.json').read_text()))
