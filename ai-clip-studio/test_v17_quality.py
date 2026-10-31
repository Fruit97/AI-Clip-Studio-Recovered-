"""Offline-only regression tests. Never contact Gemini (20 requests/day)."""
from pathlib import Path
import json
import subprocess
import pytest
import v17_quality as v17
import v15_60seconds as v15


def make_beats(lengths):
    return [{'narration': ('ก'*n), 'caption': 'ภาพจริง',
             'source_start': float(i), 'source_end':float(i+1), 'shot_id':f's{i}'}
            for i,n in enumerate(lengths)]


def test_78_7_seconds_within_one_call_speech_range():
    assert v15.MAX_SPEECH >= 78.7
    assert v15.MIN_SPEECH < 60
    assert 'around 445-535 Thai characters' in (Path(__file__).parent/'v15_60seconds.py').read_text()


def test_script_trim_preserves_beginning_and_conclusion():
    input_beats=make_beats([45]*15)
    data={'beats':input_beats, 'script':'bad prior script'}
    result=v17.enforce_script_budget(data,60)
    assert len(result['beats']) < 15
    assert result['beats'][0]['shot_id']=='s0'
    assert result['beats'][-1]['shot_id']=='s14'
    assert 390 <= result['v17_preflight']['glyphs_after'] <= 555
    assert result['script']==' '.join(b['narration'] for b in result['beats'])
    assert len(result['captions'])==len(result['beats'])
    assert len(result['highlights'])==len(result['beats'])
    assert result['v17_preflight']['additional_gemini_requests']==0


def test_script_preflight_rejects_too_short_without_tts():
    with pytest.raises(RuntimeError,match='ไม่เรียก TTS'):
        v17.enforce_script_budget({'beats': make_beats([25]*5)},60)


def test_preflight_rejects_overlong_if_only_three_beats():
    with pytest.raises(RuntimeError,match='หยุดก่อนเสียโควตาเสียง'):
        v17.enforce_script_budget({'beats': make_beats([200,200,200])},60)


def test_preflight_never_mutates_non_60_second_jobs():
    data={'beats':make_beats([200]*10),'script':'original'}
    assert v17.enforce_script_budget(data,30) is data
    assert data['script']=='original'


def test_85_second_limit_blocks_unintelligible_speedup():
    assert v15.MAX_SPEECH==85.0


def make_sine(path,seconds):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i',f'sine=frequency=460:sample_rate=24000:duration={seconds}',
        '-ac','1',str(path)],capture_output=True,text=True,timeout=90)
    assert p.returncode==0,p.stderr[-1200:]


@pytest.mark.parametrize('seconds',[46.0,56.0,64.0,75.0,78.7,84.0])
def test_voice_duration_without_extra_gemini_api(tmp_path,seconds):
    voice=tmp_path/'voice.wav';make_sine(voice,seconds)
    assert v15.ensure_voice_60(voice)==60.0
    assert abs(v15._voice_duration(voice)-60.0)<.018
    size=voice.stat().st_size
    # Resume/checkpoint: processing the same saved audio twice changes nothing
    assert v15.ensure_voice_60(voice)==60.0
    assert voice.stat().st_size==size


def test_voice_over_range_keeps_saved_file_for_resume(tmp_path):
    voice=tmp_path/'voice.wav';make_sine(voice,87.0)
    before=voice.stat().st_size
    with pytest.raises(RuntimeError,match='เสียงพากย์ยาว'):
        v15.ensure_voice_60(voice)
    assert voice.exists() and voice.stat().st_size==before


def test_v17_app_install_and_no_extra_key_calls():
    import app
    assert app.app.state.v17_no_extra_api_calls
    assert app.app.state.v17_pre_tts_script_budget
    assert app.app.state.v15_exact_minute
    assert app.app.state.v14_universal_visual_matching
    assert app.app.state.quota_aware
    assert app.app.state.retry_429 is False
    assert app.app.state.retry_read_timeout is False
    assert any(getattr(route,'path','')=='/api/v17/info' for route in app.app.routes)


def test_build_docker_covers_v17_and_static_cache():
    root=Path(__file__).parent
    assert 'v17_quality.py' in (root/'Dockerfile').read_text()
    html=(root/'site/index.html').read_text()
    assert 'data-val="60">60 วิ' in html
    assert 'app.js?v=17' in html


def test_gemini_analysis_cached_before_local_validation_failure(tmp_path,monkeypatch):
    """No second analysis API call when local normalization fails on resume."""
    import app,v11
    from pathlib import Path
    import time
    jid='eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    folder=tmp_path/jid;folder.mkdir()
    source=folder/'input.mp4';source.write_bytes(b'stub-source')
    monkeypatch.setattr(app,'WORK',tmp_path)
    monkeypatch.setattr(app,'STATUS_DIR',tmp_path/'_job_status')
    app.STATUS_DIR.mkdir(exist_ok=True)
    app.jobs.clear()
    app.jobs[jid]={'state':'queued','progress':0,'step':'queued',
                   'token':'dummy-token','created':time.time()}
    monkeypatch.setattr(app,'probe',lambda _: (40.0,False))
    monkeypatch.setattr(v11,'make_proxy',lambda src,dest:dest)
    monkeypatch.setattr(v11,'detect_shots',lambda *_:[{'id':'s000','start':0,'end':40}])
    calls=[]
    def fake_analysis(*args):
        calls.append('Gemini')
        return {'scenes':[],'beats':[{'narration':'short'}]}
    monkeypatch.setattr(v11,'analyze_proxy',fake_analysis)
    def fail_validation(*args):
        raise RuntimeError('no visually verified beats')
    monkeypatch.setattr(v11,'normalize_beats',fail_validation)
    opts={'length':15,'tone':'สารคดี','voice':'female','keep_sound':False}
    app.process(jid,str(source),'','test_fake_key_123456789',opts)
    assert app.jobs[jid]['state']=='error'
    assert (folder/'analysis-raw-v17.json').exists()
    app.process(jid,str(source),'','test_fake_key_123456789',opts)
    assert app.jobs[jid]['state']=='error'
    assert calls==['Gemini']
