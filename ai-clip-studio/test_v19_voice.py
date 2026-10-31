"""Regression for the real V18 VOICE failure with many speech pauses."""
import math
import subprocess
from array import array
from pathlib import Path
import wave
import pytest
import v18_voice as v18
import v15_60seconds as v15

def make_voice(path, seconds, quiet_gap):
    rate=24000
    pause_samples=round(quiet_gap*rate)
    blocks=13
    voice_samples=round((seconds*rate-12*pause_samples)/blocks)
    assert voice_samples>rate
    signal=array('h', (int(9000*math.sin(i*2*math.pi*370/rate))
                        for i in range(voice_samples)))
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        for n in range(blocks):
            f.writeframes(signal.tobytes())
            if n<12:
                f.writeframes(b'\x00\x00'*pause_samples)

@pytest.mark.parametrize('seconds,gap',[(43.8,.80),(44.9,.70),(45.9,.68)])
def test_false_short_narration_error_from_many_pauses(tmp_path, seconds, gap):
    import app
    wav=tmp_path/'voice.wav'
    make_voice(wav, seconds, gap)
    pauses=v18._quiet_pause_times(wav)
    assert len(pauses)>=9
    tempo=v15._voice_duration(wav)/(59.6-min(9.,.75*len(pauses)))
    assert .83<tempo<.95
    assert v15.ensure_voice_60(wav)==60
    assert abs(v15._voice_duration(wav)-60)<.018
    before=wav.stat().st_size
    assert v15.ensure_voice_60(wav)==60
    assert before==wav.stat().st_size
