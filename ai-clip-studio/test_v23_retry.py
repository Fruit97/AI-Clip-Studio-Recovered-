from types import SimpleNamespace
import pytest
import v23_retry as v23

U='https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent'

def test_recovers_503_once():
    calls=[]; waits=[]; notifications=[]
    def request(*args,**kw):
        calls.append(1)
        if len(calls)==1: raise RuntimeError('Gemini API (503): high demand')
        return {'candidates':[{'content':{'parts':[{'text':'ok'}]}}]}
    got=v23.call_with_bounded_retry(request,None,'POST',U,'dummy-key',{'json':{}},sleep=waits.append,notify_retry=lambda *x:notifications.append(x))
    assert got['candidates'] and len(calls)==2 and waits==[4] and notifications==[(1,2,4)]

def test_503_exhausted_after_three_calls_with_clear_resume():
    calls=[];waits=[]
    def request(*args,**kw):
        calls.append(1);raise RuntimeError('Gemini API (503): high demand')
    with pytest.raises(RuntimeError,match='ทำงานต่อจากจุดที่สำเร็จแล้ว'):
        v23.call_with_bounded_retry(request,None,'POST',U,'key',{},sleep=waits.append)
    assert len(calls)==3 and waits==[4,12]

@pytest.mark.parametrize('err',[RuntimeError('Gemini API (429): quota exceeded'),RuntimeError('Gemini API (500): upstream'),RuntimeError('Gemini ตอบกลับช้าเกินเวลาที่กำหนด')])
def test_no_automatic_replay_for_non_503(err):
    calls=[]
    def request(*args,**kw): calls.append(1);raise err
    with pytest.raises(RuntimeError):
        v23.call_with_bounded_retry(request,None,'POST',U,'key',{},sleep=lambda n:pytest.fail('must not sleep'))
    assert calls==[1]

def test_no_retry_on_tts_or_other_method():
    for method,url in [('POST','https://generativelanguage.googleapis.com/v1beta/interactions'),('GET',U)]:
        calls=[]
        def request(*args,**kw): calls.append(1);raise RuntimeError('Gemini API (503): high demand')
        with pytest.raises(RuntimeError,match='503'):
            v23.call_with_bounded_retry(request,None,method,url,'key',{},sleep=lambda n:pytest.fail('must not sleep'))
        assert calls==[1]

def test_context_is_job_scoped_and_restored():
    calls=[];notes=[];app=SimpleNamespace(state=SimpleNamespace(),get=lambda path:(lambda fn:fn))
    def request(*a,**kw):
        calls.append(1)
        if len(calls)==1:raise RuntimeError('Gemini API (503): high demand')
        return {'ok':True}
    def old_process(jid,*args):
        result=ns['get_json'](None,'POST',U,'key',json={})
        assert result == {'ok':True}
    ns={'get_json':request,'process':old_process,'notify':lambda *x:notes.append(x), 'app':app}
    v23.install(ns)
    # Replace the backoff with a no-wait stub; no network or Gemini calls.
    original=v23.call_with_bounded_retry
    try:
        v23.call_with_bounded_retry=lambda *a,**kw:original(*a,sleep=lambda _:None,**kw)
        ns['process']('job-abc',None,'','key',{})
    finally:
        v23.call_with_bounded_retry=original
    assert len(calls)==2 and notes and notes[0][0]=='job-abc'
    assert v23._CURRENT_JOB.get() is None
    assert ns['app'].state.retry_503_script_only


def test_v11_resume_calls_latest_wrapped_process():
    import inspect
    v11=pytest.importorskip('v11')
    assert "ns['executor'].submit(ns['process']," in inspect.getsource(v11.install)
