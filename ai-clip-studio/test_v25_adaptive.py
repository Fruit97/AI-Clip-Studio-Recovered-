"""V25 offline simulations: no real Gemini calls, no personal data."""
import sys, types, importlib
import pytest

@pytest.fixture(autouse=True)
def stub_deps(monkeypatch):
    v22=types.ModuleType('v22_scene')
    class InsufficientFootage(RuntimeError):
        def __init__(self,index,message):
            self.index=index
            super().__init__(message)
    v22.InsufficientFootage=InsufficientFootage
    monkeypatch.setitem(sys.modules,'v22_scene',v22)
    v21=types.ModuleType('v21_storyflow')
    v21.phrase_windows=lambda beats,duration:[(duration*i/len(beats),duration*(i+1)/len(beats)) for i in range(len(beats))]
    monkeypatch.setitem(sys.modules,'v21_storyflow',v21)

def shot(i,start,end,take):return {'id':f's{i}','start':start,'end':end,'take_id':take}
def beat(i,ids,chars=70):
    return {'narration':'นี่คือสาระสำคัญที่เกิดขึ้นในวิดีโอ'+str(i) if chars>30 else 'ข้อมูล '+str(i),
            'caption':f'ความรู้ {i}','shot_id':f's{ids[0]}','related_shots':[f's{j}' for j in ids],
            'source_start':float(ids[0]*6),'source_end':float(ids[0]*6+6)}

def test_synthetic_split_reuses_same_camera_take_but_no_frames_twice():
    import v25_adaptive as v25
    shots=[shot(0,0,6,'a'),shot(1,6,12,'a'),shot(2,12,18,'a')]
    result=v25.plan([beat(0,[0]),beat(1,[1])],17,18,shots,[(0,9),(9,17)])
    assert abs(sum(x['duration'] for x in result)-17)<.001
    assert result[0]['source_start']==0
    assert all(y['source_start']+0.001>=x['source_start']+x['duration'] for x,y in zip(result,result[1:]))

def test_strict_real_cut_rejected_without_independent_evidence():
    import v25_adaptive as v25
    shots=[shot(0,0,6,'a'),shot(1,6,15,'b')]
    with pytest.raises(Exception):
        v25.plan([beat(0,[0])],10,15,shots)

def test_multiple_verified_takes_forward_only():
    import v25_adaptive as v25
    shots=[shot(i,i*6,i*6+6,str(i)) for i in range(12)]
    beats=[beat(i,[i]) for i in range(12)]
    result=v25.plan(beats,60,72,shots)
    assert abs(sum(s['duration'] for s in result)-60)<.001
    assert len(set(x['shot_id'] for x in result))==12
    assert all(result[i+1]['source_start']>=result[i]['source_start']+result[i]['duration']-.0001 for i in range(len(result)-1))

def test_insufficient_evidence_fails_instead_of_padding():
    import v25_adaptive as v25
    shots=[shot(0,0,5,'a'),shot(1,5,10,'b')]
    with pytest.raises(Exception):v25.plan([beat(0,[0]),beat(1,[1])],60,100,shots)

def test_preflight_preserves_minute_when_source_supports():
    import v25_adaptive as v25
    shots=[shot(i,i*6,i*6+6,str(i)) for i in range(15)]
    beats=[beat(i,[i]) for i in range(15)]
    r=v25.preflight({'beats':beats,'_v17_target_seconds':60},shots,90)
    assert r['v25_preflight']['removed_beats']==0
    assert r['v25_preflight']['verified_takes']==15

def test_preflight_does_not_drop_to_two_beats():
    import v25_adaptive as v25
    shots=[shot(i,i*5,i*5+5,str(i)) for i in range(7)]
    beats=[beat(i,[i]) for i in range(7)]
    beats[1]['narration']*=5
    with pytest.raises(RuntimeError,match='ช่วงภาพที่ AI ยืนยันได้'):
        v25.preflight({'beats':beats,'_v17_target_seconds':60},shots,35)

def test_no_unbounded_expansion_and_no_backtrack():
    import v25_adaptive as v25
    shots=[shot(0,0,6,'a'),shot(1,6,100,'a')]
    with pytest.raises(Exception):v25.plan([beat(0,[0])],22,100,shots)

def test_prompt_contains_knowledge_grounding_and_sentence_fit(monkeypatch):
    import v25_adaptive as v25
    stub=types.ModuleType('v14_semantic')
    stub.make_prompt=lambda tc,length,tone:'original prompt'
    monkeypatch.setitem(sys.modules,'v14_semantic',stub)
    fake_app=types.SimpleNamespace(state=types.SimpleNamespace(),get=lambda u:(lambda f:f))
    ns={'app':fake_app,'APP_VERSION':'v24'}
    v25.install(ns)
    s=stub.make_prompt([],60,'สาระน่ารู้')
    assert 'original prompt' in s and '3-7' in s and 'Google-grounded facts' in s
    assert ns['APP_VERSION'].startswith('v25')
