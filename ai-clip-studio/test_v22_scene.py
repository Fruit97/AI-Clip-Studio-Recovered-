"""Actual failure prevention: v11 splits a real scene at 6 seconds, and V21 falsely rejects an 8s sentence."""
import subprocess
import pytest
import v21_storyflow as v21
import v22_scene as v22


def _beat(n, sid):
    return {'narration':'นี่คือเหตุการณ์ในคลิปต้นฉบับที่มีหลักฐานรองรับและเรากำลังสรุป'+str(n),
       'caption':'ใจความจากคลิป','shot_id':sid,'related_shots':[sid],
       'source_start':float(sid[1:])*6,'source_end':float(sid[1:])*6+6}


def test_real_take_synthetic_6s_splits_not_falsely_rejected():
    beats=[_beat(1,'s0')]
    shots=[{'id':'s0','start':0,'end':6,'take_id':'take_0000'},
           {'id':'s1','start':6,'end':12,'take_id':'take_0000'}]
    # V21 insisted on a single 6s synthetic partition per 8s sentence.
    assert shots[0]['end'] - shots[0]['start'] < 8
    cuts=v22.plan(beats,8,12,shots)
    assert len(cuts)==1 and cuts[0]['duration']==8
    assert cuts[0]['source_start']==0


def test_cannot_cross_real_scene_cut_without_independent_evidence():
    beats=[_beat(1,'s0')]
    shots=[{'id':'s0','start':0,'end':6,'take_id':'take_0000'},
           {'id':'s1','start':6,'end':12,'take_id':'take_0001'}]
    with pytest.raises(v22.InsufficientFootage):v22.plan(beats,8,12,shots)


def test_no_reuse_or_rewind_same_take_for_three_sentences():
    shots=[{'id':f's{i}','start':float(i*6),'end':float((i+1)*6),'take_id':'take_0000'} for i in range(5)]
    beats=[_beat(i,f's{i}') for i in range(3)]
    cuts=v22.plan(beats,21,30,shots)
    assert abs(sum(x['duration'] for x in cuts)-21)<.001
    assert all(b['source_start']>=a['source_start']+a['duration']-.001 for a,b in zip(cuts,cuts[1:]))


def test_preflight_removes_whole_unallocatable_sentences():
    shots=[{'id':'s0','start':0,'end':6,'take_id':'take_0000'},
           {'id':'s1','start':6,'end':12,'take_id':'take_0001'},
           {'id':'s2','start':12,'end':18,'take_id':'take_0002'},
           {'id':'s3','start':18,'end':24,'take_id':'take_0003'}]
    beats=[{'narration': 'ข้อมูลสั้นๆ'+str(i),'caption':'ข้อมูล','shot_id':f's{i}',
        'related_shots':[f's{i}'],'source_start':i*6.,'source_end':(i+1)*6.} for i in range(4)]
    beats[1]['narration']='บรรยายยาวที่กินภาพเกินกำหนดหนึ่งฉาก'*7
    d=v22.preflight({'beats':beats,'title':'หัวข้อ'},shots,24)
    assert d['v22_preflight']['removed_beats']>=1
    assert d['beats'][0]['shot_id']=='s0' and d['beats'][-1]['shot_id']=='s3'
    assert d['v22_preflight']['additional_gemini_requests']==0


def test_group_synthetic_real_video(tmp_path):
    movie=tmp_path/'source.mp4'
    cmd=['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i',
         'testsrc2=size=160x90:rate=30:duration=12','-c:v','libx264',
         '-threads','1','-preset','ultrafast',str(movie)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    assert p.returncode==0,p.stderr
    shots=[{'id':'s0','start':0,'end':6},{'id':'s1','start':6,'end':12}]
    tagged=v22.group_synthetic_shots(shots,movie,12)
    assert tagged[0]['take_id']==tagged[1]['take_id']
    cuts=v22.plan([_beat(0,'s0')],8,12,tagged)
    assert sum(c['duration'] for c in cuts)==8


def test_cached_with_group_does_not_recompute(tmp_path):
    shots=[{'id':'s0','start':0,'end':6,'take_id':'take_0000'}]
    result=v22.group_synthetic_shots(shots,tmp_path/'missing.mp4',6)
    assert result==shots
