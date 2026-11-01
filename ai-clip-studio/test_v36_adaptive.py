import sys
import pytest
import v35_continuity as v35
import app

def test_v36_three_confirmed_moments_shorter_story(tmp_path,monkeypatch):
    from types import SimpleNamespace
    sh=[{'id':f's{i}','start':i*15.,'end':(i+1)*15.,
         'take_id':'verified_take'} for i in range(3)]
    raw={'_v14_evidence_required':True,'beats':[
        {'narration':'คำบรรยายที่มีภาพต้นฉบับยืนยันตรงเหตุการณ์จริงในช่วงนี้อย่างชัดเจนและต่อเนื่องในวิดีโอ '+str(i),
         'shot_id':f's{i}','related_shots':[f's{i}'],'caption':'ภาพจากต้นฉบับ',
         'source_start':i*15.,'source_end':(i+1)*15.} for i in range(3)]}
    monkeypatch.setitem(sys.modules,'v14_semantic',SimpleNamespace(normalize=lambda a,s,d,l:a))
    monkeypatch.setitem(sys.modules,'v21_storyflow',SimpleNamespace(polish_story=lambda a:a))
    monkeypatch.setitem(sys.modules,'v17_quality',SimpleNamespace(
        MIN_CHARS=390,enforce_script_budget=lambda *a:(_ for _ in ()).throw(AssertionError('Old 390-character floor'))))
    monkeypatch.setitem(sys.modules,'v28_alignment',SimpleNamespace(
        coverage_report=lambda *a:{'evidenced_partition_seconds':45}))
    assert 240 <= v35.glyphs(raw['beats']) < 390
    selected,notes=v35.select_grounded(raw,tmp_path,sh,45,60)
    assert selected is not None,notes
    assert len(selected['beats'])==3
    assert all(b['_v35_contextual'] for b in selected['beats'])

def test_v36_short_voice_only_with_context(tmp_path):
    import app
    import v30_source_first as v30
    import v30_render_reliability as frames
    with pytest.raises(RuntimeError):
        v30.adjust_voice({},tmp_path/'none.wav',30.,60)
    tok=v35._ACTIVE.set({'adaptive':True})
    try:
        assert v30.adjust_voice({},tmp_path/'none.wav',30.,60)==30.
        mp4=tmp_path/'short.mp4';mp4.write_bytes(b'test')
        prior=frames.media_info
        frames.media_info=lambda _: (900,'30/1',30.)
        try: assert frames.finalize_frames(mp4,60)==mp4
        finally: frames.media_info=prior
    finally: v35._ACTIVE.reset(tok)

def test_v36_bad_fps_never_passes(tmp_path):
    import app
    import v30_render_reliability as frames
    mp4=tmp_path/'invalid.mp4';mp4.write_bytes(b'test')
    tok=v35._ACTIVE.set({'adaptive':True})
    prior=frames.media_info
    frames.media_info=lambda _: (900,'24/1',30.)
    try:
        with pytest.raises(RuntimeError,match='30 FPS'):
            frames.finalize_frames(mp4,60)
    finally:
        frames.media_info=prior
        v35._ACTIVE.reset(tok)
