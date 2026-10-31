"""Offline tests for adaptive proxy. No API keys, no remote requests."""
import subprocess
from pathlib import Path
import pytest
import v20_proxy
import v11


def test_profiles():
    assert v20_proxy.proxy_profiles(40)[0][:3] == (False,6,512)
    assert v20_proxy.proxy_profiles(90)[0][:3] == (True,4,480)
    assert v20_proxy.proxy_profiles(900)[0][:3] == (True,2,384)


def make_movie(path, seconds, height=360):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i',f'testsrc2=size={int(height*16/9)//2*2}x{height}:rate=30:duration={seconds}',
        '-f','lavfi','-i',f'sine=frequency=330:sample_rate=24000:duration={seconds}',
        '-c:v','libx264','-preset','ultrafast','-threads','1','-g','60',
        '-c:a','aac','-b:a','32k','-pix_fmt','yuv420p','-shortest',str(path)],
        capture_output=True,text=True,timeout=180)
    assert p.returncode == 0, p.stderr[-800:]
    return path


def test_long_source_keyframes_keep_media_time(tmp_path):
    source=make_movie(tmp_path/'source.mp4',70)
    dest=tmp_path/'proxy.mp4'
    v20_proxy.make_proxy(source,dest)
    assert v11.media_ok(dest,69)
    assert abs(v11.duration_of(dest)-v11.duration_of(source))<1
    assert v20_proxy.make_proxy(source,dest)==dest


def test_short_source_standard_decoder(tmp_path):
    source=make_movie(tmp_path/'source.mp4',4)
    dest=tmp_path/'proxy.mp4'
    assert v11.media_ok(v20_proxy.make_proxy(source,dest),3.9)


def test_failure_before_gemini(tmp_path,monkeypatch):
    source=tmp_path/'source.mp4';source.write_bytes(b'placeholder')
    monkeypatch.setattr(v11,'duration_of',lambda path: 400)
    monkeypatch.setattr(v11,'ffmpeg_run',lambda args,timeout=240: (_ for _ in ()).throw(RuntimeError('timed out')))
    with pytest.raises(RuntimeError,match='ไม่เรียก Gemini'):
        v20_proxy.make_proxy(source,tmp_path/'proxy.mp4')
    assert not list(tmp_path.glob('*.tmp.mp4'))


def test_sparse_keyframes_without_audio_keep_duration(tmp_path):
    source=tmp_path/'sparse.mp4'
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=64',
        '-c:v','libx264','-preset','ultrafast','-threads','1',
        '-g','300','-an','-pix_fmt','yuv420p',str(source)],
        capture_output=True,text=True,timeout=120)
    assert p.returncode==0,p.stderr[-800:]
    dest=tmp_path/'proxy.mp4'
    v20_proxy.make_proxy(source,dest)
    assert abs(v11.duration_of(dest)-64)<0.1
