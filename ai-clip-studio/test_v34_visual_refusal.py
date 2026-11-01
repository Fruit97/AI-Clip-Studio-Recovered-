import sys,types
from pathlib import Path
import pytest
from v34_visual_refusal import source_refusal, install, PRE_VOICE_SOURCE_PREFIX

@pytest.mark.parametrize('suffix',["", " กรุณาเพิ่มวิดีโอที่มีเนื้อหามากขึ้น", " | ตรวจภาพ: AI จับคู่หลักฐานภาพเบื้องต้นได้ 3/7 ประโยค, 4 ช็อต"])
def test_pre_tts_coverage_refusal_is_visual_not_real_voice_error(suffix):
    assert source_refusal(RuntimeError(PRE_VOICE_SOURCE_PREFIX+suffix))

@pytest.mark.parametrize('text',[
    'Gemini API (429): quota exceeded',
    'Gemini API (503): rate limited',
    'Gemini TTS error: failed',
    'FFmpeg: audio missing',
    PRE_VOICE_SOURCE_PREFIX+' Gemini API (503): unreachable',
    'เสียงพากย์ไม่มีความยาว',
])
def test_external_errors_do_not_become_visual_refusal(text):
    assert not source_refusal(RuntimeError(text))

def test_only_single_replan_and_reuse_cached_analysis(monkeypatch,tmp_path):
    fake27=types.ModuleType('v27_replan')
    fake30=types.ModuleType('v30_source_first')
    fake27.is_visual_failure=lambda exc:False
    fake30.need_deep_repair=lambda exc: isinstance(exc,RuntimeError) and 'ภาพ' in str(exc)
    fake30._JOB=types.SimpleNamespace(get=lambda:{'jid':'job1','opts':{'length':60,'tone':'กระชับ น่าติดตาม เหมาะกับคลิปสั้น'}})
    monkeypatch.setitem(sys.modules,'v27_replan',fake27)
    monkeypatch.setitem(sys.modules,'v30_source_first',fake30)
    ns={'WORK':tmp_path,'app':types.SimpleNamespace(state=types.SimpleNamespace(),get=lambda path:(lambda fn:fn))}
    install(ns)
    reason=RuntimeError(PRE_VOICE_SOURCE_PREFIX+' | ตรวจภาพ: 3/7')
    assert fake27.is_visual_failure(reason)
    assert fake30.need_deep_repair(reason)
    assert not fake27.is_visual_failure(RuntimeError('Gemini API (429): quota exceeded'))
    assert not fake30.need_deep_repair(RuntimeError('Gemini API (429): quota exceeded'))
    assert not fake30.need_deep_repair(RuntimeError('ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว แต่ยังไม่พอ'))
    f=tmp_path/'job1';f.mkdir()
    (f/'analysis-replanned-v27.json').write_text('{"beats":[]}',encoding='utf8')
    assert fake27.is_visual_failure(reason) # V27 can read cache; no API required
    assert not fake30.need_deep_repair(reason)
    assert ns['app'].state.v34_pretts_coverage_classification


def test_non_runtime_and_unrelated_error_not_retried():
    assert not source_refusal(ValueError(PRE_VOICE_SOURCE_PREFIX))
    assert not source_refusal(RuntimeError('ผลเสียงจริงสั้นเกินไป'))
