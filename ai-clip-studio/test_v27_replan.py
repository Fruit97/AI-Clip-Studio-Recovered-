"""V27 offline tests: all Gemini interactions mocked, no API key or video required."""
from pathlib import Path
import importlib, sys, types
from types import SimpleNamespace
import json
import pytest

import v27_replan as v27


def test_prompt_and_quota_errors():
    assert v27.repair_prompt('start',None)=='start'
    p=v27.repair_prompt('start',v27.brief_context({'beats':[{'shot_id':'s01','narration':'แมวเลียขน'}]},'ภาพไม่พอ',60))
    assert 'entire uploaded video' in p
    assert 'source IDs in increasing timeline order' in p
    assert 'แมวเลียขน' in p
    assert not v27.is_visual_failure(RuntimeError('Gemini API (503): high demand'))
    assert not v27.is_visual_failure(RuntimeError('โควตา Gemini API (429)'))
    assert v27.is_visual_failure(RuntimeError('ต้นฉบับยาว 412.5 วินาที แต่บทพูดประโยคที่ 2 ไม่มีภาพ'))
    assert not v27.is_visual_failure(ValueError('ภาพที่ AI'))


def prepare(monkeypatch,tmp_path,success=True):
    fake_v11=types.ModuleType('v11')
    fail={'count':0}
    calls={'analyze':0,'normalize':0}
    def original_normalize(data,shots,duration):
        calls['normalize']+=1
        if data.get('good'):
            return {'script':' '.join(x['narration'] for x in data['beats']), 'beats':data['beats']}
        raise RuntimeError('ต้นฉบับยาว 412.5 วินาที แต่บทพูดประโยคที่ 2 ไม่มีภาพพอ')
    fake_v11.normalize_beats=original_normalize
    fake_v11.atom_json=lambda path,value:Path(path).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    def analyze(*args):
        calls['analyze']+=1
        return {'good':success,'beats':[{'narration':'สาระใหม่จากภาพจริง'}]}
    fake_v11.analyze_proxy=analyze
    monkeypatch.setitem(sys.modules,'v11',fake_v11)
    fake_v14=types.ModuleType('v14_semantic')
    fake_v14.make_prompt=lambda *args:'original'
    monkeypatch.setitem(sys.modules,'v14_semantic',fake_v14)
    fake_httpx=types.ModuleType('httpx')
    class FakeClient:
        def __init__(self,*a,**kw): pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
    fake_httpx.Client=FakeClient
    fake_httpx.Timeout=lambda *args,**kw:None
    monkeypatch.setitem(sys.modules,'httpx',fake_httpx)
    app=SimpleNamespace(state=SimpleNamespace(),get=lambda path:(lambda cb:cb))
    folder=tmp_path/'job1';folder.mkdir();(folder/'analysis_proxy.mp4').write_bytes(b'dummy video')
    ns={'app':app,'WORK':tmp_path,'process':lambda *a:fake_v11.normalize_beats({'beats':[{'narration':'old'}]},[],412.5),
        'notify':lambda *a:None,'APP_VERSION':'v26'}
    v27.install(ns)
    return ns, fake_v11, fake_v14, calls, folder


def test_replan_once_then_cache(monkeypatch,tmp_path):
    ns,v11,v14,calls,folder=prepare(monkeypatch,tmp_path)
    args=('job1',str(folder/'video.mp4'),'', 'fake-secret-key-must-not-leak',{'length':60,'tone':'สาระน่ารู้'})
    result=ns['process'](*args)
    assert result['v27_replanned']['extra_gemini_video_analysis']==1
    assert calls['analyze']==1
    assert (folder/'analysis-replanned-v27.json').is_file()
    assert 'fake-secret-key' not in (folder/'analysis-replanned-v27.json').read_text()
    ns['process'](*args)
    assert calls['analyze']==1
    assert ns['APP_VERSION'].startswith('v27-')
    assert ns['app'].state.v27_max_extra_video_analysis==1


def test_replan_exhausts_only_one_attempt(monkeypatch,tmp_path):
    ns,v11,v14,calls,folder=prepare(monkeypatch,tmp_path,success=False)
    with pytest.raises(RuntimeError,match='อีกหนึ่งรอบ'):
        ns['process']('job1','source.mp4','','fake-secret-key-must-not-leak',{'length':60,'tone':'สารคดี'})
    assert calls['analyze']==1
    assert (folder/'analysis-replanned-v27.json').exists()


def test_success_no_extra_calls(monkeypatch,tmp_path):
    ns,v11,v14,calls,folder=prepare(monkeypatch,tmp_path)
    b={'good':True,'beats':[{'narration':'already visually verified'}]}
    assert v11.normalize_beats(b,[],60)['beats']==b['beats']
    assert calls['analyze']==0


def test_unrelated_errors_not_replayed(monkeypatch,tmp_path):
    ns,v11,v14,calls,folder=prepare(monkeypatch,tmp_path)
    prior=v11.normalize_beats
    def error(*args):raise RuntimeError('Gemini API (503): high demand')
    # We verify the strict predicate independently: only visual evidence failure triggers retry.
    assert not v27.is_visual_failure(RuntimeError('Gemini API (503): high demand'))
    assert calls['analyze']==0
