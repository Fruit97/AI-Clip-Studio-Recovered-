import pytest
import sys,types
from v31_illustrative import make_illustrative, illustrative_cuts, glyphs

def raw_model(beats=14, grounded=True, real_evidence=3, target_subject='เสือโคร่ง'):
    spans = [{'id':f's{i}','start':i*7.,'end':i*7.+6.,'take_id':f't{i}'} for i in range(5)]
    scene=[{'id':f's{i}','description':f'เสือโคร่งกำลังเดินอยู่ในป่าไม้ในคลิปต้นฉบับ ฉาก {i}', 'tags':['เสือโคร่ง','ป่าไม้']} for i in range(5)]
    base='เสือโคร่งเป็นสัตว์นักล่าที่มีวิธีปรับตัวเข้ากับธรรมชาติและมีบทบาทในระบบนิเวศ '
    entries=[]
    for i in range(beats):
        matched=[{'id':f's{i%3}','score':.88,'evidence':'มองเห็นเสือโคร่งเดินผ่านป่าตรงจุดนี้จริง'}] if i<real_evidence else []
        entries.append({'narration':base+f'หัวข้อย่อยที่ {i} ซึ่งผ่านแหล่งข้อมูลแล้ว',
                        'caption':f'ข้อมูลสาระเรื่องเสือโคร่ง {i}',
                        'visual_keywords':[target_subject], 'visual_matches':matched})
    return {'title':'เสือโคร่ง','summary':'สาระน่ารู้','knowledge_sources':[{'url':'https://example.org/verified'}] if grounded else [],
            '_v14_evidence_required':True,'_v14_candidate_shots':[s['id'] for s in spans],
            'scenes':scene,'beats':entries},spans

def test_grounded_fallback_allows_same_subject_facts():
    raw,shots=raw_model(14)
    result=make_illustrative(raw,shots,60)
    assert 6<=len(result['beats'])<=14
    assert result['v31_fallback']['visually_verified_anchors']==3
    assert result['v31_fallback']['accepted_facts']==len(result['beats'])
    assert all(b['caption'].startswith('ภาพประกอบ') for b in result['beats'])
    assert result['knowledge_sources']

@pytest.mark.parametrize('target', [60,90,120])
def test_all_durations_have_usable_script_and_audio_time(target,monkeypatch):
    raw,shots=raw_model(24)
    result=make_illustrative(raw,shots,target)
    fake=types.SimpleNamespace(phrase_windows=lambda beats,secs,wav:[(secs*i/len(beats),secs*(i+1)/len(beats)) for i in range(len(beats))])
    monkeypatch.setitem(sys.modules,'v21_storyflow',fake)
    edits=illustrative_cuts(result['beats'],float(target),float(max(s['end'] for s in shots)),shots)
    assert abs(sum(x['duration'] for x in edits)-target)<.02
    assert edits[0]['voice_start']==0
    assert edits[-1]['voice_start']+edits[-1]['duration']==pytest.approx(target,abs=.02)
    assert any(x['_v31_repeat_index'] for x in edits)
    assert all(x['shot_id'] in {s['id'] for s in shots} for x in edits)
    assert all(x['source_start']>=0 for x in edits)
    assert all(x['source_start']+x['duration']<=next(s['end'] for s in shots if s['id']==x['shot_id'])+.001 for x in edits)
    assert all(x['caption'].startswith('ภาพประกอบ') for x in edits)

def test_no_grounding_rejected():
    raw,shots=raw_model(14,grounded=False)
    with pytest.raises(RuntimeError,match='แหล่ง'):make_illustrative(raw,shots,60)

def test_missing_model_anchor_rejected():
    raw,shots=raw_model(15,real_evidence=0)
    with pytest.raises(RuntimeError,match='ไม่มีภาพ'):make_illustrative(raw,shots,60)

def test_cross_topic_not_allowed():
    raw,shots=raw_model(14,real_evidence=2,target_subject='ไดโนเสาร์')
    with pytest.raises(RuntimeError,match='ยังไม่พอ'):make_illustrative(raw,shots,60)

def test_invented_visual_assertions_are_dropped():
    raw,shots=raw_model(14)
    raw['beats'][3]['narration']='ในภาพนี้เราจะเห็นเหตุการณ์ชัดเจน'*10
    result=make_illustrative(raw,shots,60)
    assert result['v31_fallback']['excluded_facts']==1
    assert all('ในภาพนี้' not in x['narration'] for x in result['beats'])

def test_low_confidence_not_eligible():
    raw,shots=raw_model(14,real_evidence=3)
    for b in raw['beats'][:3]:b['visual_matches'][0]['score']=.5
    with pytest.raises(RuntimeError,match='ไม่มีภาพ'):make_illustrative(raw,shots,60)

def test_short_script_never_triggers_paid_tts():
    raw,shots=raw_model(3)
    with pytest.raises(RuntimeError,match='ไม่พอ'):make_illustrative(raw,shots,60)

def test_live_hook_uses_only_model_anchored_fallback_when_strict_fails(tmp_path,monkeypatch):
    import json
    import v31_illustrative as v31
    raw,shots=raw_model(14)
    jid='b'*32
    (tmp_path/jid).mkdir()
    calls=[]
    def blocked(*args):
        calls.append('strict')
        raise RuntimeError('หลักฐานภาพไม่พอสำหรับบท')
    v11=types.ModuleType('v11');v11.normalize_beats=blocked;v11.time_beats=lambda *a:[]
    v14=types.ModuleType('v14_semantic');v14.make_prompt=lambda *a:'original prompt'
    v30=types.ModuleType('v30_source_first')
    v30.need_deep_repair=lambda exc: True
    v30._JOB=types.SimpleNamespace(get=lambda:{'jid':jid,'opts':{'tone':'สาระน่ารู้','length':60}})
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v30_source_first',v30)
    class App:
        def __init__(self):self.state=types.SimpleNamespace()
        def get(self,path):return lambda fn:fn
    ns={'WORK':tmp_path,'app':App(),'process':lambda *a:None,'notify':lambda *a:None}
    v31.install(ns)
    result=v11.normalize_beats(raw,shots,85.)
    assert calls==['strict']
    assert result['v31_fallback']['mode']=='educational_illustration'
    assert 'V31 EDUCATIONAL MODE' in v14.make_prompt([],60,'สาระน่ารู้')
    assert 'V31 EDUCATIONAL MODE' not in v14.make_prompt([],60,'สารคดี')
    assert ns['app'].state.v31_grounded_educational_illustration


def test_live_hook_never_bypasses_non_knowledge_strict_failure(tmp_path,monkeypatch):
    import v31_illustrative as v31
    raw,shots=raw_model(14)
    v11=types.ModuleType('v11')
    v11.normalize_beats=lambda *a:(_ for _ in ()).throw(RuntimeError('ภาพไม่พอ'))
    v11.time_beats=lambda *a:[]
    v14=types.ModuleType('v14_semantic');v14.make_prompt=lambda *a:'original'
    v30=types.ModuleType('v30_source_first')
    v30.need_deep_repair=lambda exc: True
    v30._JOB=types.SimpleNamespace(get=lambda:{'jid':'fake','opts':{'tone':'ข่าว','length':60}})
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v30_source_first',v30)
    class App:
        def __init__(self):self.state=types.SimpleNamespace()
        def get(self,path):return lambda fn:fn
    ns={'WORK':tmp_path,'app':App(),'process':lambda *a:None}
    v31.install(ns)
    with pytest.raises(RuntimeError,match='ภาพไม่พอ'):
        v11.normalize_beats(raw,shots,85.)
