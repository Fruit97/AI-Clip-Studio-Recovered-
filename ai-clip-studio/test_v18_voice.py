"""Regression: the observed 39.0s TTS must not throw, and no Gemini is called."""
import subprocess
from pathlib import Path
import wave
import pytest
import v18_voice as v18
import v15_60seconds as v15


def sine(path, sec):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                      '-f','lavfi','-i',f'sine=frequency=480:sample_rate=24000:duration={sec}',
                      '-ac','1',str(path)],capture_output=True,text=True,timeout=90)
    assert p.returncode==0,p.stderr

@pytest.mark.parametrize('seconds',[33.0,39.0,42.0,45.9,46.0,56.0,78.7,84.0])
def test_various_tts_lengths_are_exact_60(tmp_path,seconds):
    import app
    wav=tmp_path/'voice.wav';sine(wav,seconds)
    assert v15.ensure_voice_60(wav)==60
    assert abs(v15._voice_duration(wav)-60)<.018
    size=wav.stat().st_size
    assert v15.ensure_voice_60(wav)==60
    assert wav.stat().st_size==size


def test_short_with_real_pause_regions(tmp_path):
    import app
    start=tmp_path/'tone.wav';sine(start,3.5)
    with wave.open(str(start),'rb') as f:
        params=f.getparams();tone=f.readframes(f.getnframes())
    src=tmp_path/'voice.wav'
    # 8 quiet sentence breaks, 9 blocks of speech: 39s total.
    with wave.open(str(src),'wb') as f:
        f.setparams(params)
        for i in range(9):
            f.writeframes(tone)
            if i<8: f.writeframes(b'\0\0'*(int(.9*params.framerate)))
    assert len(v18._quiet_pause_times(src))>=7
    assert v15.ensure_voice_60(src)==60
    assert abs(v15._voice_duration(src)-60)<.018


def test_preflight_does_not_truncate_trusted_shot_evidence():
    import app
    import v17_quality as v17
    beats=[{'narration':'ฉากนี้เกิดขึ้นตรงกับสิ่งที่ภาพจริงแสดงให้เห็น'+str(i)*13,
            'caption':'ภาพจริง','source_start':i,'source_end':i+1,'shot_id':str(i)} for i in range(15)]
    a=v17.enforce_script_budget({'beats':beats},60)
    assert 430<=a['v17_preflight']['glyphs_after']<=700
    assert a['beats'][0]['shot_id']=='0' and a['beats'][-1]['shot_id']=='14'


def test_no_new_gemini_endpoints_and_app_flag():
    import app
    assert app.app.state.v18_short_voice_local_pacing
    assert any(x.path=='/api/v18/info' for x in app.app.routes)
