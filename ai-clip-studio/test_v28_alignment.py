import sys
import types
import pytest
import v28_alignment as v28


def item(i, start, end):
    return {'id': f's{i}', 'start': start, 'end': end}


def valid(shot_id, score=.92, desc='ตรงกับแมวตัวที่อยู่ในภาพ'):
    return {'id': shot_id, 'score': score, 'evidence': desc}


def test_counts_only_original_valid_scored_evidence():
    a = {'scenes':[{'id':'s0','description':'แมวเลียขนตัวเอง','tags':['แมว']},
                   {'id':'s1','description':'แมวตัวเดียวกันกำลังนั่ง','tags':['แมว']}],
         '_v14_candidate_shots':['s0','s1'],
         'beats':[{'visual_matches':[valid('s0'),valid('s1',.77)]},
                  {'visual_matches':[valid('s0'),valid('s999')]},
                  {'visual_matches':[]} ]}
    r = v28.coverage_report(a,[item(0,0,6),item(1,6,12)])
    assert r['narration_beats'] == 3 and r['beats_with_model_evidence']==2
    assert r['distinct_evidenced_shots']==1 and r['evidenced_partition_seconds']==6


def test_coverage_unions_overlapping_time_without_double_counting():
    raw = {'scenes':[{'id':'s0','description':'แมว'}, {'id':'s1','description':'แมว'}],
           'beats':[{'visual_matches':[valid('s0'),valid('s1')]}]}
    r=v28.coverage_report(raw,[item(0,0,6),item(1,4,12)])
    assert r['evidenced_partition_seconds']==12.0


def test_coverage_rejects_fake_model_confidence_and_malformed_proof():
    raw={'scenes':[{'id':'s0','description':'แมว'}],
         'beats':[{'visual_matches':[valid('s0',1.2),valid('s0',.75),valid('s0',.9,'x')]}]}
    assert v28.coverage_report(raw,[item(0,0,5)])['distinct_evidenced_shots']==0


def test_no_private_narration_or_keys_in_coverage_note():
    a={'narration_beats':4,'beats_with_model_evidence':2,
       'distinct_evidenced_shots':3,'evidenced_partition_seconds':18}
    s=v28.error_note(a)
    assert '2/4' in s and '18' in s and 'secret' not in s


def test_empty_analysis_is_stable():
    assert v28.coverage_report({},[])['evidenced_partition_seconds']==0


def test_install_routes_and_wrapping_error(monkeypatch,tmp_path):
    v11=types.ModuleType('v11')
    class App:
        def __init__(self):self.state=types.SimpleNamespace();self.routes={}
        def get(self,path):
            def deco(fn):self.routes[path]=fn;return fn
            return deco
    app=App()
    def original(raw,shots,duration):raise RuntimeError('ภาพที่ยืนยันได้ไม่เพียงพอ')
    v11.normalize_beats=original
    v11.atom_json=lambda path, obj: path.write_text(__import__('json').dumps(obj),encoding='utf-8')
    v27=types.ModuleType('v27_replan')
    class FakeJob:
        def get(self):return {'jid':'test','opts':{'length':60}}
    v27._JOB=FakeJob()
    monkeypatch.setitem(sys.modules,'v11',v11)
    v14=types.ModuleType('v14_semantic')
    v14.make_prompt=lambda *a: 'old'
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v27_replan',v27)
    (tmp_path/'test').mkdir()
    ns={'app':app,'WORK':tmp_path}
    v28.install(ns)
    with pytest.raises(RuntimeError,match='ตรวจภาพ'):
        v11.normalize_beats({'beats':[]},[],120)
    assert (tmp_path/'test'/'v28-visual-audit.json').exists()
    assert app.routes['/api/v28/info']()['minimum_seconds']==60

def test_knowledge_prompt_preserves_visual_truth_and_source_requirement(monkeypatch,tmp_path):
    v11=types.ModuleType('v11');v11.normalize_beats=lambda a,b,c:a
    v27=types.ModuleType('v27_replan')
    v27._JOB=types.SimpleNamespace(get=lambda:None)
    v14=types.ModuleType('v14_semantic')
    v14.make_prompt=lambda x,y,z:'ORIGINAL GUARDED VIDEO PROMPT'
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v27_replan',v27)
    app=types.SimpleNamespace(state=types.SimpleNamespace(),get=lambda u:(lambda f:f))
    v28.install({'app':app,'WORK':tmp_path})
    s=v14.make_prompt([],60,'สาระน่ารู้')
    assert 'distinctive real' in s or 'distinctive' in s
    assert 'Scores must be genuinely >= 0.78' in s
    s2=v14.make_prompt([],90,'สรุปคลิป')
    assert 'EVENT RULE' in s2 and 'EDUCATIONAL VISUAL RULE' not in s2
