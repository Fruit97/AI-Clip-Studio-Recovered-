import json
from pathlib import Path
import subprocess
import pytest
import v15_60seconds as v15

def ff(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=150)
    assert p.returncode==0,p.stderr[-1600:]

def sound(path,seconds):
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
       '-f','lavfi','-i',f'sine=frequency=440:sample_rate=24000:duration={seconds}',
       '-ac','1',str(path)])

def test_sound_56_to_exact_60(tmp_path):
    wav=tmp_path/'voice.wav';sound(wav,56)
    assert v15.ensure_voice_60(wav)==60
    assert abs(v15._voice_duration(wav)-60)<.018
    # Running again must not change the recording.
    length=wav.stat().st_size
    v15.ensure_voice_60(wav)
    assert wav.stat().st_size==length

def test_sound_64_to_exact_60(tmp_path):
    wav=tmp_path/'voice.wav';sound(wav,64)
    assert v15.ensure_voice_60(wav)==60
    assert abs(v15._voice_duration(wav)-60)<.018

def test_extremely_short_sound_does_not_fake_60s(tmp_path):
    wav=tmp_path/'voice.wav';sound(wav,18)
    with pytest.raises(RuntimeError,match='เสียงพากย์ยาว'):
        v15.ensure_voice_60(wav)

def test_final_mp4_1800_cfr_frames(tmp_path):
    raw=tmp_path/'raw.mp4'
    out=tmp_path/'finished.mp4'
    ff(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
         '-f','lavfi','-i','testsrc2=size=240x136:rate=30:duration=60',
         '-f','lavfi','-i','sine=frequency=700:sample_rate=44100:duration=60',
         '-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','64k','-shortest',str(raw)])
    v15.finalize_mp4_60(raw,out)
    p=subprocess.check_output(['ffprobe','-v','error','-show_entries',
         'format=duration:stream=codec_type,nb_frames,avg_frame_rate',
         '-of','json',str(out)])
    d=json.loads(p)
    v=next(x for x in d['streams'] if x['codec_type']=='video')
    assert v['nb_frames']=='1800' and v['avg_frame_rate']=='30/1'
    assert abs(float(d['format']['duration'])-60)<.05
    assert any(x['codec_type']=='audio' for x in d['streams'])
