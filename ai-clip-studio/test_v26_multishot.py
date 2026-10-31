"""V26 offline tests; zero Gemini requests and no real user files."""
import importlib
import sys
import types
import pytest

@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    v22 = types.ModuleType('v22_scene')
    class InsufficientFootage(RuntimeError):
        def __init__(self, index, msg):
            self.index = index
            super().__init__(msg)
    v22.InsufficientFootage = InsufficientFootage
    monkeypatch.setitem(sys.modules, 'v22_scene', v22)
    v21 = types.ModuleType('v21_storyflow')
    v21.phrase_windows = lambda beats,duration:[(i*duration/len(beats),(i+1)*duration/len(beats)) for i in range(len(beats))]
    monkeypatch.setitem(sys.modules, 'v21_storyflow', v21)

def shot(i,a,b,tid=None):
    return {'id':f's{i}', 'start':a, 'end':b, 'take_id':tid or f'take{i}'}

def beat(i,ids,text=None):
    return {'narration':text or ('สาระน่ารู้และข้อเท็จจริงที่ได้จากคลิปนี้คือ' + str(i))*3,
            'caption':f'ข้อเท็จจริง {i}',
            'shot_id':f's{ids[0]}',
            'related_shots':[f's{j}' for j in ids],
            'source_start':float(ids[0])*6, 'source_end':float(ids[0])*6+6}

def forward(cuts):
    return all(b['source_start'] >= a['source_start']+a['duration']-.001 for a,b in zip(cuts,cuts[1:]))

def test_one_sentence_may_cover_two_independently_verified_real_takes():
    from v26_multishot import plan
    shots=[shot(0,0,4),shot(1,4,8)]
    cuts=plan([beat(0,[0,1])],8,8,shots,[(0,8)])
    assert len(cuts)==2 and [c['shot_id'] for c in cuts]==['s0','s1']
    assert abs(sum(c['duration'] for c in cuts)-8)<.001 and forward(cuts)
    assert all(c['v26_independently_verified'] for c in cuts)

def test_cross_real_cut_without_independent_approval_still_fails():
    from v26_multishot import plan
    shots=[shot(0,0,4),shot(1,4,8)]
    with pytest.raises(Exception):plan([beat(0,[0])],8,8,shots,[(0,8)])

def test_long_first_beat_but_good_remaining_60s_can_be_dropped():
    from v26_multishot import preflight
    shots=[shot(0,0,4)]+[shot(i,i*8,i*8+8) for i in range(1,11)]
    b=[beat(0,[0],text='คำอธิบายยาวๆ'*15)]+[beat(i,[i],text='เรื่องราวสาระน่ารู้ประกอบวิดีโอชุดนี้อย่างละเอียดพอสมควร'+str(i)) for i in range(1,11)]
    data=preflight({'beats':b,'_v17_target_seconds':60},shots,412.5)
    assert len(data['beats'])==10
    assert data['v26_preflight']['removed_beats']==1
    assert data['v26_preflight']['removed_samples'][0]['index']==1
    assert data['v26_preflight']['estimated_speech_seconds'] >= 55

def test_insufficient_story_does_not_drop_start_just_to_pad():
    from v26_multishot import preflight
    shots=[shot(i,i*6,i*6+6) for i in range(4)]
    b=[beat(i,[i]) for i in range(4)]
    b[0]['narration']='อะไรยาวๆ'*15
    with pytest.raises(RuntimeError,match='ส่วนที่เหลือไม่พอ'):
        preflight({'beats':b,'_v17_target_seconds':60},shots,412.5)

def test_all_matched_sections_in_source_order_without_repeat():
    from v26_multishot import plan
    shots=[shot(i,i*6,i*6+6) for i in range(12)]
    b=[beat(i,[i*2,i*2+1]) for i in range(6)]
    cuts=plan(b,60,72,shots,[(i*10,(i+1)*10) for i in range(6)])
    assert abs(sum(c['duration'] for c in cuts)-60)<.001
    assert forward(cuts)
    assert all(b['voice_start']>=a['voice_start']+a['duration']-.001 for a,b in zip(cuts,cuts[1:]))

def test_synthetic_splits_inside_same_take_remain_continuous():
    from v26_multishot import plan
    shots=[shot(i,i*6,(i+1)*6,'a') for i in range(4)]
    cuts=plan([beat(0,[0])],16,24,shots,[(0,16)])
    assert abs(sum(c['duration'] for c in cuts)-16)<.001
    assert all(c['v26_take_id']=='a' for c in cuts)
    assert forward(cuts)

def test_90s_and_120s_durations_retained_in_planner():
    from v26_multishot import plan
    for target,n in [(90,15),(120,20)]:
        shots=[shot(i,i*6,i*6+6) for i in range(n)]
        bs=[beat(i,[i]) for i in range(n)]
        cuts=plan(bs,target,target,shots)
        assert round(sum(c['duration'] for c in cuts))==target and forward(cuts)

def test_install_hooks_latest_v25_and_v22_and_app_state(monkeypatch):
    import v26_multishot as v26
    v25=types.ModuleType('v25_adaptive')
    v25.plan=lambda *args:None;v25.preflight=lambda *args:None
    v14=types.ModuleType('v14_semantic')
    v14.make_prompt=lambda *args:'base'
    monkeypatch.setitem(sys.modules,'v25_adaptive',v25)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    state=types.SimpleNamespace()
    app=types.SimpleNamespace(state=state,get=lambda u:(lambda f:f))
    ns={'app':app,'APP_VERSION':'v25'}
    v26.install(ns)
    assert v25.plan is v26.plan and sys.modules['v22_scene'].plan is v26.plan
    assert v25.preflight is v26.preflight and sys.modules['v22_scene'].preflight is v26.preflight
    assert ns['APP_VERSION'].startswith('v26-')
    assert 'V26 SHOT-BUDGET RULE' in v14.make_prompt([],60,'สาระน่ารู้')
    assert state.v26_multi_verified_takes

@pytest.mark.parametrize('target', [60,90,120])
def test_no_synthetic_source_padding_when_insufficient(target):
    from v26_multishot import plan
    shots=[shot(i,i*6,(i+1)*6) for i in range(4)]
    b=[beat(i,[i]) for i in range(4)]
    with pytest.raises(Exception):plan(b,target,target+300,shots)
