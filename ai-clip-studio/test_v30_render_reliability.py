"""Current-contract checks: exact 30 fps and no redundant render on resume."""
from pathlib import Path
from fastapi import FastAPI
import v30_render_reliability as reliability


def test_exact_media_rejects_nonexistent(tmp_path):
    assert not reliability.exact_media(tmp_path / 'not-found.mp4', 60)


def test_tiny_drift_only(tmp_path, monkeypatch):
    source=tmp_path/'result.mp4'
    source.write_bytes(b'not a real mp4')
    monkeypatch.setattr(reliability,'media_info',lambda path: (60*30-8,'30/1',60.0))
    try:
        reliability.finalize_frames(source,60)
    except RuntimeError as exc:
        assert 'ผิดปกติ' in str(exc)
    else:
        raise AssertionError('Must not hide missing 8 frames')


def test_finished_checkpoint_not_rendered_twice(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    cached=tmp_path/'result.mp4'
    cached.write_bytes(b'saved')
    (tmp_path/'v21_success.marker').write_text('ok')
    def should_not_reencode(*a,**k):
        raise AssertionError('Completed result must not re-render')
    fake_v11=SimpleNamespace(render_timeline=should_not_reencode)
    monkeypatch.setitem(sys.modules,'v11',fake_v11)
    monkeypatch.setattr(reliability,'exact_media',lambda path,target: path==cached and target==120)
    ns={'app':FastAPI()}
    reliability.install(ns)
    assert fake_v11.render_timeline(ns,'job',tmp_path/'input.mp4',tmp_path/'voice.wav',tmp_path,
                               [],120,True,120,{'length':120},[])==cached
    assert ns['app'].state.v30_render_reliability
