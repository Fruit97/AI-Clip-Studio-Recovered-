"""V35 regression tests: video-length statistics + strict real-camera take boundaries."""
import json,sys,types,subprocess
from pathlib import Path
import pytest
import v35_continuity as v35

@pytest.fixture(autouse=True)
def fixture_windows(monkeypatch):
    # Project's v21.phrase_windows is imported in integration tests on GitHub.
    # In this standalone suite use equal-length natural voice windows.
    monkeypatch.setitem(sys.modules,'v21_storyflow',types.SimpleNamespace(
        phrase_windows=lambda beats,duration,wav=None:[(i*duration/len(beats),(i+1)*duration/len(beats)) for i in range(len(beats))]))


def shots_412():
    # Camera continuity detected on user's actual 412.4 sec footage:
    # first camera take 0-320.93, next 320.97-392.26, last 392.27-412.4.
    points=[]
    for i in range(69):
        a=i*6.0;b=min(a+6,412.4)
        if a<318:take='real_take_0'
        elif a<390:take='real_take_1'
        else:take='real_take_2'
        points.append({'id':f's{i:03}','start':a,'end':b,'take_id':take})
    return points


def beats8():
    return [dict(narration='ผู้บรรยายเล่าเหตุการณ์ที่เห็นจริงในคลิปต้นฉบับ และอธิบายรายละเอียดของสิ่งที่กำลังทำในฉากอย่างชัดเจน '+str(i),
                 caption='คนทำงานในลานบ้าน',shot_id=f's{i:03}',related_shots=[f's{i:03}'],
                 source_start=i*6,source_end=i*6+6,_v35_contextual=True)
            for i in range(8)]


def test_real_412_second_source_footage_continuity_schedule():
    cuts=v35.continuous_cuts(beats8(),60,412.4,shots_412())
    assert abs(sum(c['duration'] for c in cuts)-60)<.01
    assert cuts[0]['source_start']==0
    assert cuts[-1]['source_start']+cuts[-1]['duration']<=320.93
    assert all(b['source_start']+1e-5>=a['source_start']+a['duration'] for a,b in zip(cuts,cuts[1:]))
    assert all('real_take_0' in c['_v35_same_take'] for c in cuts)


def test_one_short_camera_take_must_not_be_extended_over_unrelated_cut():
    beats=beats8()
    shots=[dict(id=f's{i:03}',start=6*i,end=6*i+6,take_id=f'take_{i}') for i in range(8)]
    with pytest.raises(RuntimeError,match='camera take'):
        v35.continuous_cuts(beats,60,412.4,shots)


def test_unknown_takes_always_isolated():
    ss=[{'id':'s1','start':0,'end':6},{'id':'s2','start':6,'end':12}]
    assert len(v35.takes(ss,100))==2

@pytest.mark.parametrize('error',[
    'Gemini API (429): quota exceeded','Gemini API (503): service unavailable',
    'FFmpeg: decode failed','Gemini TTS error','read timeout'
])
def test_actual_api_or_audio_errors_never_swallowed(error,monkeypatch):
    monkeypatch.setitem(sys.modules,'v32_recovery',types.SimpleNamespace(visual_planning_failure=lambda e:True))
    assert not v35.eligible_failure(RuntimeError(error))


def test_3_of_7_then_8_of_8_is_recovered_from_raw_checkpoints(tmp_path,monkeypatch):
    from types import SimpleNamespace
    sh=shots_412()
    def model(n,matched):
        return {'_v14_evidence_required':True,'_v14_candidate_shots':[s['id'] for s in sh],
            'title':'บทสรุปจากต้นฉบับ', 'summary':'เหตุการณ์จากวิดีโอจริง',
            'scenes':[{'id':s['id'],'description':'คนทำกิจกรรมที่ลานบ้านจริง'} for s in sh],
            'beats':[{'narration':'คนในวิดีโอเล่าเรื่องและสาธิตวิธีทำกิจกรรมที่ลานบ้านอย่างเป็นลำดับตามภาพจริง พร้อมการอธิบายที่ชัดเจนสำหรับผู้ชม '+str(i),
              'caption':'เนื้อหาจากวิดีโอต้นฉบับ', 'visual_matches':([{'id':f's{i:03}', 'score':.93,
              'evidence':'มองเห็นบุคคลกำลังอธิบายและทำกิจกรรมอยู่ที่ลานบ้านจริง'}] if i<matched else []),
              'shot_id':f's{i:03}'} for i in range(n)]}
    before=model(7,3);after=model(8,8)
    (tmp_path/'analysis-replanned-v27.json').write_text(json.dumps(after,ensure_ascii=False),'utf8')
    # Real v14.normalize from project will validate same strict score/evidence.
    def normalize(item,shots,dur,legacy):
        li={s['id']:s for s in shots}
        valid=[]
        for b in item['beats']:
            ms=b['visual_matches']
            if not ms:continue
            s=li[ms[0]['id']];c=b.copy();c.update(related_shots=[s['id']],source_start=s['start'],source_end=s['end'])
            valid.append(c)
        if not valid:raise RuntimeError('no evidence')
        item['beats']=valid
        return item
    def polish(item):
        item['beats']=sorted(item['beats'],key=lambda x:x['source_start'])
        return item
    def budget(item,target):
        if v35.glyphs(item['beats'])<430:raise RuntimeError('insufficient narration')
        return item
    monkeypatch.setitem(sys.modules,'v14_semantic',SimpleNamespace(normalize=normalize))
    monkeypatch.setitem(sys.modules,'v17_quality',SimpleNamespace(enforce_script_budget=budget))
    monkeypatch.setitem(sys.modules,'v21_storyflow',SimpleNamespace(polish_story=polish))
    monkeypatch.setitem(sys.modules,'v28_alignment',SimpleNamespace(coverage_report=lambda x,y:{'evidenced_partition_seconds':47.7}))
    result,diags=v35.select_grounded(before,tmp_path,sh,412.4,60)
    assert result is not None
    assert result['_v35_contextual']['source']=='replanned-v27'
    assert len(result['beats'])==8
    assert result['_v35_contextual']['physical_take_seconds']>=300
    assert all(c['caption'].startswith('ภาพประกอบจากต้นฉบับ') for c in result['beats'])


def test_source_isolation_after_camera_cut():
    sh=shots_412();b=beats8()
    # An irrelevant source take 330s later is NEVER appended to beat number 1.
    assert v35.takes(sh,412.4)['real_take_0'][1]<325
    assert v35.continuous_cuts(b,60,412.4,sh)[-1]['source_start']<90


@pytest.mark.parametrize('target',[60,90,120])
def test_real_long_take_three_output_targets_when_evidence_is_distributed(target):
    sh=shots_412()
    # Each beat independently belongs to an anchored partition of the same
    # physical camera take. Never claim an earlier anchor proves a later scene.
    indices=[int(i*target/(12*6)) for i in range(12)]
    beats=[{'narration':'คำบรรยายจากภาพต้นฉบับ','caption':'ภาพประกอบจากต้นฉบับ',
            'shot_id':f's{k:03}','related_shots':[f's{k:03}']} for k in indices]
    cuts=v35.continuous_cuts(beats,target,412.4,sh)
    assert abs(sum(x['duration'] for x in cuts)-target)<.02
    assert cuts[-1]['source_start']+cuts[-1]['duration']<=320.93
    assert all(b['source_start']>=a['source_start']+a['duration']-.002
               for a,b in zip(cuts,cuts[1:]))
