"""V30 no-key tests: three durations, evidence constraints, retry caching, real media."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import types
import wave
import pytest
import v30_source_first as mod

@pytest.mark.parametrize('seconds', [60, 90, 120])
def test_duration_budget_and_rejection(seconds):
    n=mod.TARGETS[seconds]
    value={'beats':[{'narration':'ก'*n}]}
    assert mod.validate_script(value,seconds)==n
    with pytest.raises(RuntimeError, match='ก่อนสร้างเสียง'):
        mod.validate_script({'beats':[{'narration':'ก'*(n-1)}]},seconds)

@pytest.mark.parametrize('detail', ['Gemini API (429): quota','Gemini API (503): high demand','TTS error','FFmpeg video error'])
def test_never_repeat_unrelated_errors(detail):
    assert not mod.need_deep_repair(RuntimeError(detail))

def test_visual_failures_only_trigger_replan():
    assert mod.need_deep_repair(RuntimeError('ภาพที่ยืนยันได้มีช็อตไม่พอ'))
    assert not mod.need_deep_repair(ValueError('ภาพต้นฉบับไม่พอ'))

def test_prompt_keeps_strict_source_provenance():
    for sec in (60,90,120):
        prompt=mod.deep_prompt('original',{'length':sec})
        assert '0.78' in prompt and 'without replay' in prompt and str(sec) in prompt
        assert 'Never fabricate' in prompt
    assert mod.deep_prompt('original',None)=='original'

def test_never_repeat_tts_when_very_short(tmp_path):
    data=tmp_path/'voice.wav'
    data.write_bytes(b'mock')
    with pytest.raises(RuntimeError,match='สั้นกว่าเป้าหมาย'):
        mod.adjust_voice({'ffmpeg_run':lambda *a,**kw:None,'duration_of':lambda _:9.5},data,70,90)


def ff(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
    assert p.returncode==0, p.stderr[-2500:]


def probe(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=nb_frames,avg_frame_rate,codec_type',
                      '-of','json',str(path)],capture_output=True,text=True,timeout=30)
    assert p.returncode==0, p.stderr
    return json.loads(p.stdout)


def test_voice_adjustment_never_adds_large_silence(tmp_path):
    src=tmp_path/'speech.wav'
    ff(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-f','lavfi',
        '-i','sine=frequency=250:sample_rate=24000:duration=4.83',
        '-ac','1','-c:a','pcm_s16le','-y',str(src)])
    def ffmpeg_run(args,timeout):
        ff(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y']+args)
    def duration_of(path):return float(probe(path)['format']['duration'])
    seconds=mod.adjust_voice({'ffmpeg_run':ffmpeg_run,'duration_of':duration_of},src,4.83,5)
    assert seconds>=4.985 and seconds<5.15
    assert abs(duration_of(src)-seconds)<.02


@pytest.mark.parametrize('target', [60,90,120])
def test_real_mp4_all_lengths_with_audio_and_frames(tmp_path, target):
    """Decodes actual media using FFmpeg and checks durations, CFR video, audio."""
    video=tmp_path/f'synth_{target}.mp4'
    ff(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
        '-f','lavfi','-i',f'testsrc2=size=72x128:rate=30:duration={target}',
        '-f','lavfi','-i',f'sine=frequency=330:sample_rate=24000:duration={target}',
        '-map','0:v','-map','1:a','-c:v','libx264','-threads','1','-preset','ultrafast',
        '-pix_fmt','yuv420p','-r','30','-c:a','aac','-shortest','-movflags','+faststart',str(video)])
    d=probe(video)
    assert abs(float(d['format']['duration'])-target)<.15
    vids=[s for s in d['streams'] if s['codec_type']=='video']
    assert len(vids)==1 and vids[0]['avg_frame_rate']=='30/1'
    assert abs(int(vids[0]['nb_frames'])-30*target)<3
    assert any(s['codec_type']=='audio' for s in d['streams'])


def test_version_marker():
    assert mod.VERSION.startswith('v30-')


def test_plan_forward_coverage_with_actual_v26_rules(monkeypatch):
    """24 independently evidenced scenes can give a real 120s forward-only cut plan."""
    import importlib.util
    path=Path(__file__).parent
    p=path/'v26_multishot.py'
    if not p.exists():
        pytest.skip('V26 source unavailable in standalone unit environment')
    spec=importlib.util.spec_from_file_location('v26_multishot',p)
    v26=importlib.util.module_from_spec(spec);spec.loader.exec_module(v26)
    class E(Exception):
        def __init__(self,i,message):self.index=i;super().__init__(message)
    monkeypatch.setitem(sys.modules,'v22_scene',types.SimpleNamespace(InsufficientFootage=E))
    monkeypatch.setitem(sys.modules,'v21_storyflow',types.SimpleNamespace(
        phrase_windows=lambda beats,duration:[(i*duration/len(beats),(i+1)*duration/len(beats)) for i in range(len(beats))]))
    shots=[{'id':f's{i:03}','start':i*6.,'end':(i+1)*6.,'take_id':f'take_{i:03}'} for i in range(65)]
    beats=[{'narration':'สมมติคำพากย์ฉากที่มีหลักฐานภาพ','shot_id':f's{i:03}',
            'related_shots':[]} for i in range(24)]
    result=v26.plan(beats,120,390,shots)
    assert abs(sum(z['duration'] for z in result)-120)<.05
    assert all(b['source_start'] >= a['source_start']+a['duration']-.002 for a,b in zip(result,result[1:]))


def test_deep_analysis_one_request_then_cached_on_resume(tmp_path,monkeypatch):
    """No Gemini TTS call until evidence passes and cache stops duplicate video calls."""
    import importlib
    v11=types.ModuleType('v11')
    v14=types.ModuleType('v14_semantic')
    v27=types.ModuleType('v27_replan')
    v14.make_prompt=lambda *args:'prompt'
    v27._JOB=types.SimpleNamespace(get=lambda:None)
    call_count=[]
    target=120
    good={'beats':[{'narration':'ภ'*mod.TARGETS[target]}]}
    def scan(ns,client,proxy,key,duration,shots,target,tone):
        call_count.append('SCAN')
        assert proxy.exists() and target==120
        assert mod._FOCUS.get()['length']==120
        return json.loads(json.dumps(good))
    v11.analyze_proxy=scan
    v11.atom_json=lambda path,val:Path(path).write_text(json.dumps(val,ensure_ascii=False),encoding='utf-8')
    def normalize(raw,shots,dur):
        if raw.get('unusable'):raise RuntimeError('ภาพที่ยืนยันได้มีช็อตไม่พอ')
        return raw
    v11.normalize_beats=normalize
    v11.ffmpeg_run=lambda *args,**kw:None
    v11.duration_of=lambda x:120.
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v27_replan',v27)
    class App:
        def __init__(self): self.state=types.SimpleNamespace()
        def get(self,path):return lambda fn:fn
    jid='a'*32
    (tmp_path/jid).mkdir()
    (tmp_path/jid/'analysis_proxy.mp4').write_bytes(b'proxy')
    outputs=[]
    def oldprocess(jid,src,link,key,opts):
        result=v11.normalize_beats({'unusable':True,'beats':[]},[],412.)
        outputs.append(result)
    ns={'WORK':tmp_path,'app':App(),'process':oldprocess,
        'tts':lambda *args:120.,'notify':lambda *args:None}
    mod.install(ns)
    for i in range(2):
        ns['process'](jid,'source.mp4','','dummy_key_01234567890',{'length':120,'tone':'สาระน่ารู้'})
    assert call_count==['SCAN']
    assert len(outputs)==2 and all(mod.characters(x)==mod.TARGETS[target] for x in outputs)
    assert (tmp_path/jid/'analysis-deep-v30.json').exists()


def test_deep_reanalysis_cannot_invent_sufficient_material(tmp_path, monkeypatch):
    import json
    v11=types.ModuleType('v11')
    v14=types.ModuleType('v14_semantic')
    v27=types.ModuleType('v27_replan')
    v14.make_prompt=lambda *a:'original'
    v11.normalize_beats=lambda raw,shots,dur:raw
    v11.analyze_proxy=lambda *a:{'beats':[{'narration':'ก'*550}]}
    v11.atom_json=lambda p,v:Path(p).write_text(json.dumps(v),encoding='utf8')
    v27._JOB=types.SimpleNamespace(get=lambda:None)
    monkeypatch.setitem(sys.modules,'v11',v11)
    monkeypatch.setitem(sys.modules,'v14_semantic',v14)
    monkeypatch.setitem(sys.modules,'v27_replan',v27)
    class App:
        def __init__(self): self.state=types.SimpleNamespace()
        def get(self,p):return lambda fn:fn
    jid='c'*32
    (tmp_path/jid).mkdir()
    (tmp_path/jid/'analysis_proxy.mp4').write_bytes(b'mock')
    def prior(*args):
        return v11.normalize_beats({'beats':[{'narration':'ก'*400}]},[],412)
    ns={'WORK':tmp_path,'app':App(),'process':prior,'tts':lambda *a:120,
        'notify':lambda *a:None}
    mod.install(ns)
    with pytest.raises(RuntimeError,match='เชิงลึก'):
        ns['process'](jid,'source','','fake_key',{'length':120,'tone':'ข่าว'})
    data=json.loads((tmp_path/jid/'v30-capacity-report.json').read_text())
    assert data['target_seconds']==120 and data['supported_script_chars']==550
