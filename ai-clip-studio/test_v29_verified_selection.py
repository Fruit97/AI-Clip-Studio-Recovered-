"""Offline V29 regressions; zero network requests, tokens or user media."""
import json
import sys
import types
import pytest


def test_v14_prefers_unused_evidence_when_both_are_genuinely_supported():
    import v14_semantic as v14
    shots=[{'id':'s001','start':0,'end':6},{'id':'s002','start':6,'end':12}]
    scene=lambda x:{'id':x,'description':'คนกำลังยืนอธิบายข้อมูลในห้อง','tags':['คน']}
    match=lambda sid,score:{'id':sid,'score':score,'evidence':'ภาพคนกำลังอธิบายหน้ากล้องในห้องเดียวกัน'}
    beat=lambda text:{'narration':text,'caption':text,
                     'visual_matches':[match('s001',.95),match('s002',.85)]}
    raw={'_v14_evidence_required':True,'_v14_candidate_shots':['s001','s002'],
         'scenes':[scene('s001'),scene('s002')],
         'beats':[beat('ผู้พูดกำลังอธิบายประเด็นแรก'),beat('ผู้พูดกำลังอธิบายประเด็นถัดมา')]}
    out=v14.normalize(raw,shots,12,lambda *a:None)
    assert [x['shot_id'] for x in out['beats']]==['s001','s002']
    assert all(x['visual_match_score'] >= .78 for x in out['beats'])


def test_v28_diagnostic_keeps_evidence_before_downstream_mutation(monkeypatch,tmp_path):
    import v28_alignment as v28
    v11=types.ModuleType('v11')
    def mutating_normalize(raw,shots,duration):
        raw['beats']=[{'narration':'เรื่องที่ผ่านการตรวจแล้ว','shot_id':'s001'}]
        raise RuntimeError('ภาพที่ยืนยันได้ไม่เพียงพอต่อการเล่าเรื่อง')
    v11.normalize_beats=mutating_normalize
    v11.atom_json=lambda path,obj:path.write_text(json.dumps(obj),encoding='utf-8')
    v27=types.ModuleType('v27_replan')
    v27._JOB=types.SimpleNamespace(get=lambda:{'jid':'test','opts':{'length':60}})
    v14=types.ModuleType('v14_semantic')
    v14.make_prompt=lambda *args:'prompt'
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v27_replan',v27)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    class App:
        def __init__(self):self.state=types.SimpleNamespace()
        def get(self,path):return lambda func:func
    (tmp_path/'test').mkdir()
    v28.install({'app':App(),'WORK':tmp_path})
    raw={'_v14_candidate_shots':['s001'],
         'scenes':[{'id':'s001','description':'คนที่อยู่ในภาพกำลังพูด'}],
         'beats':[{'visual_matches':[{'id':'s001','score':.92,
                    'evidence':'คนที่อยู่ในภาพกำลังพูดอยู่ตรงกล้อง'}]}]}
    with pytest.raises(RuntimeError,match='1/1 ประโยค'):
        v11.normalize_beats(raw,[{'id':'s001','start':0,'end':6}],412.5)
    stored=json.loads((tmp_path/'test'/'v28-visual-audit.json').read_text('utf-8'))
    assert stored['initial']['beats_with_model_evidence']==1
    assert stored['initial']['distinct_evidenced_shots']==1
    assert 'visual_matches' not in raw['beats'][0]  # confirms mutation occurred, yet audit is correct


def test_v29_version_marker_and_guards():
    import v29_verified_selection as v29
    app=types.SimpleNamespace(state=types.SimpleNamespace(),get=lambda path:(lambda fn:fn))
    ns={'app':app}
    v29.install(ns)
    assert ns['APP_VERSION'].startswith('v29-')
    assert app.state.v29_fresh_supported_shot_first
    assert app.state.v29_raw_evidence_audit_preserved
    assert ns['_V29_INSTALLED']
