"""V21 editorial timing and offline media tests (zero Gemini calls)."""
import subprocess
from pathlib import Path
import pytest
import v21_storyflow as v21


def example_beats():
    return [
        {'narration': 'ประเด็นแรกคือสัตว์ตัวนี้กำลังวิ่งผ่านทุ่ง','caption': 'สัตว์วิ่งผ่านทุ่ง',
         'shot_id':'s0','related_shots':['s0'],'source_start':0,'source_end':9},
        {'narration': 'จากนั้นมันก็เดินผ่านลำธารไปอีกด้านหนึ่ง','caption': 'เดินผ่านลำธาร',
         'shot_id':'s1','related_shots':['s1'],'source_start':9,'source_end':18},
        {'narration': 'สุดท้ายมันกลับไปหาเพื่อนที่อยู่ใกล้ต้นไม้','caption': 'กลับไปหาเพื่อน',
         'shot_id':'s2','related_shots':['s2'],'source_start':18,'source_end':27},
    ]


def shots():
    return [{'id':f's{i}','start':i*9.,'end':(i+1)*9.} for i in range(3)]


def test_prompt_focuses_on_main_idea_and_evidence():
    p=v21.editorial_prompt(lambda *_:'BASE',[],60,'สารคดี')
    assert 'central idea' in p and 'takeaways' in p and 'CHRONOLOGICAL' in p
    assert 'FIRST spoken Thai sentence' in p
    assert 'Do not revisit' in p and 'do not add a second model request' in p


def test_removes_duplicate_narration_and_orders_story():
    data={'title':'สัตว์ในทุ่ง','summary':'เรื่องสัตว์',
          'beats': [example_beats()[1],example_beats()[0],example_beats()[1],example_beats()[2]]}
    a=v21.polish_story(data)
    assert [b['shot_id'] for b in a['beats']]==['s0','s1','s2']
    assert len(a['script'].split())>=3
    assert a['v21_story']['avoided_identical_narrations']==1


def test_forward_only_shots_have_no_repeats_or_backtracks():
    beats=example_beats()
    timeline=v21.sequential_shots(beats,21.,27.,shots())
    assert len(timeline)>=3
    for i in range(1,len(timeline)):
        previous=timeline[i-1]
        current=timeline[i]
        assert current['source_start']>=previous['source_start']+previous['duration']-.001
    assert abs(sum(t['duration'] for t in timeline)-21)<.01
    assert [x['shot_id'] for x in timeline]==['s0','s1','s2']


def test_no_replay_when_few_verified_frames():
    with pytest.raises(RuntimeError,match='ไม่วนกลับฉากเดิม'):
        v21.sequential_shots(example_beats(),37,27,shots())


def test_one_long_shot_chunking_stays_continuous():
    beat=[{'narration':'นี่คือคลิปยาวที่ถ่ายต่อเนื่องตลอดเวลา',
           'caption':'ภาพต่อเนื่อง','shot_id':'s0','related_shots':['s0']}]
    c=v21.sequential_shots(beat,17,30,[{'id':'s0','start':0,'end':30}])
    assert len(c)==3
    assert c[1]['source_start']==pytest.approx(c[0]['duration'],abs=.001)
    assert c[2]['source_start']==pytest.approx(c[0]['duration']+c[1]['duration'],abs=.001)


def test_phrase_windows_sums_duration_and_minimum():
    windows=v21.phrase_windows(example_beats(),21)
    assert windows[0][0]==0
    assert windows[-1][1]==21
    assert all(a<b for a,b in windows)


def test_natural_voice_audio_is_not_stretched(tmp_path):
    import app,v11
    assert app.app.state.v21_natural_speech
    wav=tmp_path/'voice.wav'
    r=subprocess.run(['ffmpeg','-v','error','-nostdin','-y',
      '-f','lavfi','-i','sine=frequency=350:sample_rate=24000:duration=39',
      '-ac','1',str(wav)],capture_output=True,text=True,timeout=70)
    assert r.returncode==0, r.stderr
    before=wav.read_bytes()
    tok=v21._ACTIVE.set(True)
    try:
        import v15_60seconds as v15
        assert v15.ensure_voice_60(wav)==pytest.approx(39.,abs=.03)
    finally:v21._ACTIVE.reset(tok)
    assert wav.read_bytes()==before


def test_continuous_soundtrack_final_mux(tmp_path):
    import v11
    raw=tmp_path/'raw.mp4';voice=tmp_path/'voice.wav';result=tmp_path/'result.mp4'
    for args in [
        ['-f','lavfi','-i','color=size=160x90:rate=30:duration=4',
         '-f','lavfi','-i','anullsrc=r=24000:cl=mono',
         '-t','4','-c:v','libx264','-threads','1','-preset','ultrafast','-c:a','aac',str(raw)],
        ['-f','lavfi','-i','sine=frequency=350:sample_rate=24000:duration=4',
         '-ac','1',str(voice)]]:
        p=subprocess.run(['ffmpeg','-v','error','-nostdin','-y']+args,
                         capture_output=True,text=True,timeout=70)
        assert p.returncode==0,p.stderr
    v21.mux_continuous_voice(raw,result,voice,4)
    assert v11.media_ok(result,3.9)
    assert abs(v11.duration_of(result)-4)<.1


def test_early_repeated_shot_rejected_before_paid_tts():
    beats=[{'narration':f'เหตุการณ์ที่มีข้อมูลลำดับ {i} แตกต่างกัน',
            'caption':f'ข้อมูล {i}', 'source_start':0.0,'source_end':6.0,
            'shot_id':'s0'} for i in range(12)]
    with pytest.raises(RuntimeError,match='ก่อนเรียก Gemini TTS'):
        v21.polish_story({'beats':beats,'title':'คลิปที่มีช็อตเดียว'})
