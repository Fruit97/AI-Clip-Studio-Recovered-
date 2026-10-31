"""V17: source-grounded script budget *before* paid TTS. No new API requests.

V15 expected long scripts (620-820 Thai characters), and Gemini returned 78.7s
TTS for a requested 60s. This wrapper keeps the semantic shot evidence intact
while cutting redundant *whole narration beats* before TTS.
"""
from __future__ import annotations
import re

VERSION = 'v17-budgeted-source-grounded-2026-10-31'
MAX_CHARS = 555
MIN_CHARS = 390

def glyphs(s):
    return len(re.sub(r'\s+', '', str(s)))


def enforce_script_budget(result, target_seconds):
    """Trim entire evidenced middle beats, keep hook and conclusion.

    Never truncate a sentence and never attach the words of one beat to a
    different video shot. Refuse insufficiently grounded material before TTS.
    """
    if int(target_seconds) != 60:
        return result
    beats = list(result.get('beats') or [])
    if not beats:
        raise RuntimeError('ไม่มีฉากจริงที่ใช้เล่าเรื่องหนึ่งนาทีได้')

    def count(items):
        return sum(glyphs(b.get('narration', '')) for b in items)

    original_count = count(beats)
    dropped = 0
    while count(beats) > MAX_CHARS and len(beats) > 4:
        # Preserve the first hook and last resolution. Prefer removing the
        # longest middle beat so we drop as few supported scenes as possible.
        idx = max(range(1, len(beats)-1), key=lambda i: (glyphs(beats[i].get('narration', '')), -i))
        beats.pop(idx)
        dropped += 1
    remaining_count = count(beats)
    if remaining_count > MAX_CHARS:
        raise RuntimeError('บทพากย์ยังยาวเกินสำหรับคลิปหนึ่งนาทีหลังตรวจฉากแล้ว กรุณาใช้ต้นฉบับที่มีเนื้อหากระชับขึ้น (หยุดก่อนเสียโควตาเสียง)')
    if remaining_count < MIN_CHARS:
        raise RuntimeError('ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที ไม่เรียก TTS เพื่อป้องกันเสียโควตา กรุณาเพิ่มวิดีโอที่มีเนื้อหามากขึ้น')
    result['beats'] = beats
    result['script'] = ' '.join(b['narration'] for b in beats)
    result['captions'] = [b.get('caption', b['narration']) for b in beats]
    result['highlights'] = [
        {'start': b['source_start'], 'end': b['source_end']}
        for b in beats if 'source_start' in b and 'source_end' in b
    ]
    if isinstance(result.get('visual_matching_report'), dict):
        result['visual_matching_report']['accepted'] = len(beats)
        result['visual_matching_report']['pruned_for_duration'] = dropped
    result['v17_preflight'] = {
        'target_seconds': 60,
        'glyphs_before': original_count,
        'glyphs_after': remaining_count,
        'removed_beats': dropped,
        'additional_gemini_requests': 0,
    }
    return result


def install(ns):
    if ns.get('_V17_INSTALLED'):
        return
    import v11
    previous_analyze = v11.analyze_proxy
    previous_normalize = v11.normalize_beats

    def analyze_proxy(ns1, client, proxy, key, duration, shots, length, tone):
        data = previous_analyze(ns1, client, proxy, key, duration, shots, length, tone)
        data['_v17_target_seconds'] = int(length)
        return data

    def normalize_beats(analysis, shots, duration):
        result = previous_normalize(analysis, shots, duration)
        # Checkpoint-based older jobs have no marker; they are still supported
        # by V15's idempotent WAV normalization at the RENDER stage.
        return enforce_script_budget(result, analysis.get('_v17_target_seconds', 0))

    v11.analyze_proxy = analyze_proxy
    v11.normalize_beats = normalize_beats
    ns['_V17_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v17_pre_tts_script_budget = True
    ns['app'].state.v17_no_extra_api_calls = True
    @ns['app'].get('/api/v17/info')
    def info():
        return {
            'version': VERSION,
            'target_seconds': 60,
            'strict_pre_tts_budget': True,
            'script_glyphs': [MIN_CHARS, MAX_CHARS],
            'tts_api_retries_for_duration': 0,
            'maximum_saved_voice_seconds': 85,
            'resume_uses_cached_wav': True,
            'limitation': 'Gemini TTS length varies; cannot guarantee every request fits 60 seconds',
        }
