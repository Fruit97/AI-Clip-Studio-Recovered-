import httpx
import pytest
from fastapi import FastAPI
import v13_safety


def make_ns(prior):
    ns={'get_json':prior,'app':FastAPI()}
    v13_safety.install(ns)
    return ns


def test_429_not_retried_and_clear_message():
    calls=[]
    def failing(*a,**kw):
        calls.append(1)
        raise RuntimeError('Gemini API (429): quota exceeded')
    ns=make_ns(failing)
    with pytest.raises(RuntimeError,match='โควตา'):
        ns['get_json'](None,'POST','https://generativelanguage.googleapis.com/v1beta/x','fake-key')
    assert len(calls)==1


def test_read_timeout_never_replays_post():
    calls=[]
    def failing(*a,**kw):
        calls.append(1)
        raise httpx.ReadTimeout('read timed out')
    ns=make_ns(failing)
    with pytest.raises(RuntimeError,match='โควตาซ้ำ'):
        ns['get_json'](None,'POST','https://generativelanguage.googleapis.com/v1beta/x','fake-key')
    assert len(calls)==1


def test_503_is_not_automatically_retried():
    calls=[]
    def failing(*a,**kw):
        calls.append(1)
        raise RuntimeError('Gemini API (503): high demand')
    ns=make_ns(failing)
    with pytest.raises(RuntimeError,match='503'):
        ns['get_json'](None,'POST','https://generativelanguage.googleapis.com/v1beta/x','fake-key')
    assert len(calls)==1


def test_500_is_not_automatically_retried():
    calls=[]
    def failing(*a,**kw):
        calls.append(1)
        raise RuntimeError('Gemini API (500): upstream issue')
    ns=make_ns(failing)
    with pytest.raises(RuntimeError,match='ไม่เรียก API ซ้ำ'):
        ns['get_json'](None,'POST','https://generativelanguage.googleapis.com/v1beta/x','fake-key')
    assert len(calls)==1


def test_live_app_wired_to_v11_v12_v13():
    import app
    assert app.APP_VERSION in (v13_safety.VERSION, __import__('v14_semantic').VERSION, __import__('v15_60seconds').VERSION, __import__('v17_quality').VERSION, __import__('v18_voice').VERSION, __import__('v20_proxy').VERSION, __import__('v21_storyflow').VERSION, __import__('v22_scene').VERSION, __import__('v23_retry').VERSION, __import__('v24_minute_knowledge').VERSION, __import__('v25_adaptive').VERSION, __import__('v26_multishot').VERSION, __import__('v27_replan').VERSION, __import__('v28_alignment').VERSION, __import__('v29_verified_selection').VERSION, __import__('v30_source_first').VERSION, __import__('v31_illustrative').VERSION, __import__('v32_recovery').VERSION)
    assert app.app.state.v11_semantic_grounded
    assert app.app.state.v12_capacity_fallback
    assert app.app.state.quota_aware
    assert app.app.state.retry_429 is False
    assert any(getattr(x,'path',None)=='/api/jobs/{jid}/resume' for x in app.app.routes)
