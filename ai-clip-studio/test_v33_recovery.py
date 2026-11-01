import sys, types, json
from pathlib import Path
import pytest
from v33_recovery import merge_grounded_responses


def _facts(shots, count, confirmed, prefix):
    subject='เสือโคร่ง'
    beats=[]
    for i in range(count):
        sid=shots[i % len(shots)]['id']
        v={'id':sid,'score':0.92,'evidence':'วิดีโอนี้แสดงเสือโคร่งเดินในป่าอย่างชัดเจน'}
        beats.append({'narration':f'{subject} เป็นสัตว์ป่า มีพฤติกรรมสำคัญในระบบนิเวศต่างกันหัวข้อ {prefix} ข้อ {i} ซึ่งได้รับการตรวจสอบจากแหล่งข้อมูล',
             'caption':f'{subject} {prefix} {i}', 'shot_id':sid,
             'visual_keywords':[subject], 'visual_matches':[v] if i<confirmed else []})
    return {'_v14_evidence_required':True,'_v14_candidate_shots':[s['id'] for s in shots],
        'knowledge_sources':[{'url':f'https://example.org/{prefix}','title':'Grounded simulated source'}],
        'scenes':[{'id':s['id'],'description':'เสือโคร่งกำลังเดินในป่าต้นไม้','tags':['เสือโคร่ง']} for s in shots],
        'beats':beats}


def test_merge_uses_only_verified_model_shot_ids_and_citations(tmp_path,monkeypatch):
    fake=types.ModuleType('v32_recovery')
    fake.read_candidates=lambda initial,folder:[('initial',initial),('replanned-v27',json.loads((Path(folder)/'analysis-replanned-v27.json').read_text()))]
    monkeypatch.setitem(sys.modules,'v32_recovery',fake)
    shots=[{'id':f's{i:03}', 'start':i*5.97,'end':(i+1)*5.97} for i in range(70)]
    a=_facts(shots[:5],14,5,'แรก')
    b=_facts(shots[5:10],5,3,'สอง')
    (tmp_path/'analysis-replanned-v27.json').write_text(json.dumps(b,ensure_ascii=False))
    combined,report=merge_grounded_responses(a,tmp_path,shots)
    assert combined and report['sources_examined']==2
    assert report['valid_direct_anchors']==8
    assert report['distinct_direct_shots']==8
    assert len(combined['beats'])==19
    assert len(combined['knowledge_sources'])==2
    assert set(x['id'] for x in combined['scenes'])=={f's{i:03}' for i in list(range(5))+[5,6,7]}
    assert all(b.get('visual_matches')==[] or b['visual_matches'][0]['id'] in combined['_v14_candidate_shots'] for b in combined['beats'])


def test_missing_citations_or_invalid_scores_are_not_fabricated(tmp_path,monkeypatch):
    fake=types.ModuleType('v32_recovery');fake.read_candidates=lambda initial,folder:[('initial',initial)]
    monkeypatch.setitem(sys.modules,'v32_recovery',fake)
    shots=[{'id':'s0','start':0.,'end':6.}]
    a=_facts(shots,2,2,'แรก');a['knowledge_sources']=[]
    combined,report=merge_grounded_responses(a,tmp_path,shots)
    assert combined is None and report['grounded_sources']==0
    a=_facts(shots,2,2,'แรก')
    for beat in a['beats']:beat['visual_matches'][0]['score']=.65
    combined,report=merge_grounded_responses(a,tmp_path,shots)
    assert combined is None and report['distinct_direct_shots']==0


def test_out_of_range_or_unobserved_id_does_not_count(tmp_path,monkeypatch):
    fake=types.ModuleType('v32_recovery');fake.read_candidates=lambda initial,folder:[('initial',initial)]
    monkeypatch.setitem(sys.modules,'v32_recovery',fake)
    shots=[{'id':'s0','start':0.,'end':6.}]
    a=_facts(shots,2,2,'แรก')
    for beat in a['beats']:beat['visual_matches'][0]['id']='fictional'
    combined,report=merge_grounded_responses(a,tmp_path,shots)
    assert combined is None and report['distinct_direct_shots']==0


def test_installed_wrapper_uses_cached_facts_after_old_visual_failure(tmp_path,monkeypatch):
    from v33_recovery import install
    shots=[{'id':f's{i:03}','start':i*6.,'end':(i+1)*6.} for i in range(10)]
    initial=_facts(shots[:5],14,5,'เริ่มต้น')
    replan=_facts(shots[5:],5,3,'วางบทใหม่')
    job=tmp_path/'job123';job.mkdir();(job/'analysis-replanned-v27.json').write_text(json.dumps(replan,ensure_ascii=False))
    v11=types.ModuleType('v11')
    def old(*args):raise RuntimeError('ตรวจภาพและบทครบทั้งรอบแรก รอบวางบทใหม่ และรอบลึกแล้ว แต่ยังไม่พอ')
    v11.normalize_beats=old;v11.atom_json=lambda path,data:Path(path).write_text(json.dumps(data))
    v30=types.ModuleType('v30_source_first');v30._JOB=types.SimpleNamespace(get=lambda:{'jid':'job123','opts':{'tone':'สาระน่ารู้','length':60}})
    v32=types.ModuleType('v32_recovery');v32.visual_planning_failure=lambda e:False
    v32.read_candidates=lambda initial,folder:[('initial',initial),('replanned',json.loads((Path(folder)/'analysis-replanned-v27.json').read_text()))]
    v31=types.ModuleType('v31_illustrative')
    def fake_make_illustrative(raw,shots,target):
        assert len(raw['knowledge_sources'])==2
        assert len(raw['beats'])==19
        assert target==60
        return {'script':'test','v31_fallback':{'accepted_facts':19},'beats':raw['beats']}
    v31.make_illustrative=fake_make_illustrative
    for module in (v11,v30,v32,v31):monkeypatch.setitem(sys.modules,module.__name__,module)
    class FakeApp:
        def __init__(self):self.state=types.SimpleNamespace()
        def get(self,path):return lambda f:f
    ns={'app':FakeApp(),'WORK':tmp_path,'notify':lambda *args:None}
    install(ns)
    result=v11.normalize_beats(initial,shots,412.5)
    assert result['v33_recovery']['selected_grounded_sources']==2
    assert json.loads((job/'v33-coverage.json').read_text())['status']=='selected'
    assert ns['app'].state.v33_multi_analysis_recovery


def test_installed_wrapper_never_swallows_api_errors(tmp_path,monkeypatch):
    from v33_recovery import install
    v11=types.ModuleType('v11')
    v11.normalize_beats=lambda *a:(_ for _ in ()).throw(RuntimeError('Gemini API (429): quota exceeded'))
    v30=types.ModuleType('v30_source_first');v30._JOB=types.SimpleNamespace(get=lambda:{'jid':'job123','opts':{'tone':'สาระน่ารู้','length':60}})
    v32=types.ModuleType('v32_recovery');v32.visual_planning_failure=lambda e:False
    v31=types.ModuleType('v31_illustrative')
    for module in (v11,v30,v32,v31):monkeypatch.setitem(sys.modules,module.__name__,module)
    class FakeApp:
        def __init__(self):self.state=types.SimpleNamespace()
        def get(self,path):return lambda f:f
    ns={'app':FakeApp(),'WORK':tmp_path}
    install(ns)
    with pytest.raises(RuntimeError,match='429'):
        v11.normalize_beats({},[],412.5)
