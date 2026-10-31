"""V18: one-request voice pacing for short Gemini TTS responses.

No Gemini request is made here. Use moderate pitch-preserving time stretch and
insert small editorial pauses ONLY at detected quiet gaps. Exact PCM frame count
is written locally so cached TTS is not wasted during an error/resume.
"""
from __future__ import annotations

from array import array
import math
import os
from pathlib import Path
import sys
import wave

VERSION = 'v18-voice-pacing-quota-safe-2026-10-31'
TARGET = 60.0
RATE = 48000


def _quiet_pause_times(path):
    """Time locations of demonstrably quiet stretches, using PCM, no speech model."""
    try:
        with wave.open(str(path), 'rb') as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2 or f.getcomptype() != 'NONE':
                return []
            sr = f.getframerate()
            data = array('h')
            data.frombytes(f.readframes(f.getnframes()))
        if sys.byteorder != 'little':
            data.byteswap()
        step = max(1, sr // 40)  # 25ms
        rms = []
        for i in range(0, len(data), step):
            block = data[i:i+step]
            rms.append(math.sqrt(sum(int(x)*int(x) for x in block) / len(block)))
        if not rms: return []
        peak = max(rms)
        if peak < 100: return []  # near-silent recording; no meaningful speech gaps
        threshold = max(120, min(500, peak * .028))
        points = []
        start = None
        for idx, energy in enumerate(rms + [peak]):
            if energy <= threshold and start is None:
                start = idx
            elif energy > threshold and start is not None:
                if idx - start >= 4:
                    mid = (start + idx) * step / (2 * sr)
                    if 1.4 <= mid <= (len(data) / sr) - 1.4:
                        points.append((idx - start, mid))
                start = None
        # Use up to 12 well-separated breaks, prioritizing the clearest quiet runs.
        chosen = []
        for _length, sec in sorted(points, reverse=True):
            if all(abs(sec - x) >= 1.7 for x in chosen):
                chosen.append(sec)
                if len(chosen) == 12: break
        return sorted(chosen)
    except (OSError, EOFError, wave.Error, ValueError):
        return []


def fix_short_voice(wav):
    """Convert a saved 33-46s PCM narration into exactly 60s without a TTS call.

    Natural quiet boundaries receive 0.5-0.9s editorial rests, allowing a
    smaller tempo adjustment. If no real speech gaps exist, all time correction
    is pitch-preserving FFmpeg atempo (which may sound slow; we never cut words).
    """
    import v11
    wav = Path(wav)
    seconds = v11.duration_of(wav)
    if abs(seconds - TARGET) < .018:
        return TARGET
    if not (33.0 <= seconds < 46.0):
        raise RuntimeError(f'เสียงพากย์ {seconds:.1f} วินาที ไม่สามารถปรับให้เป็น 60 วินาทีโดยไม่ทำให้ผิดธรรมชาติ')
    pauses = _quiet_pause_times(wav)
    planned_gap = min(9.0, .75 * len(pauses))
    target_spoken = 59.6 - planned_gap
    tempo = seconds / target_spoken
    # For 39s with no pauses: tempo ~0.654. With 8 breaks: tempo ~0.728.
    if not (.55 <= tempo <= .83):
        raise RuntimeError('เสียงพากย์สั้นเกินไปสำหรับปรับเป็นหนึ่งนาที')
    stretched = wav.with_name('v18_voice_stretched.tmp.wav')
    assembled = wav.with_name('v18_voice_60.tmp.wav')
    try:
        v11.ffmpeg_run(['-i', str(wav), '-af', f'atempo={tempo:.9f},aresample={RATE}',
                        '-ac', '1', '-ar', str(RATE), '-c:a', 'pcm_s16le', str(stretched)], timeout=95)
        with wave.open(str(stretched), 'rb') as reader:
            if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or reader.getframerate() != RATE:
                raise RuntimeError('รูปแบบไฟล์ WAV หลังปรับความเร็วไม่ถูกต้อง')
            audio = reader.readframes(reader.getnframes())
        count = len(audio) // 2
        required = round(TARGET * RATE) - count
        if required < 0:
            raise RuntimeError('เสียงพากย์ที่ปรับความเร็วยังยาวเกิน 60 วินาที')
        # At most 0.9s per quiet break. Keep at least a small 0.2-0.4s outro.
        available = max(0, required - int(.30 * RATE))
        pause_frames = min(available, len(pauses) * int(.9 * RATE))
        pause_positions = sorted(set(min(count, max(0, round(p / tempo * RATE))) for p in pauses))
        allocations = []
        if pause_positions and pause_frames:
            q, rem = divmod(pause_frames, len(pause_positions))
            allocations = [(p, q + int(i < rem)) for i, p in enumerate(pause_positions)]
        parts = []
        previous = 0
        for pos, gap in allocations:
            parts.append(audio[2*previous:2*pos])
            parts.append(b'\x00\x00' * gap)
            previous = pos
        parts.append(audio[2*previous:])
        used_gap = sum(g for _, g in allocations)
        parts.append(b'\x00\x00' * (required - used_gap))
        with wave.open(str(assembled), 'wb') as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(RATE)
            writer.writeframes(b''.join(parts))
        if abs(v11.duration_of(assembled) - TARGET) > .018:
            raise RuntimeError('สร้างเสียง 60 วินาทีไม่สมบูรณ์')
        os.replace(assembled, wav)
        return TARGET
    finally:
        stretched.unlink(missing_ok=True)
        assembled.unlink(missing_ok=True)


def install(ns):
    if ns.get('_V18_INSTALLED'):
        return
    import v15_60seconds as v15
    import v17_quality as v17
    old_voice = v15.ensure_voice_60
    def ensure_voice_60(wav):
        seconds = v15._voice_duration(wav)
        if 33 <= seconds < 46:
            return fix_short_voice(wav)
        return old_voice(wav)
    v15.ensure_voice_60 = ensure_voice_60
    # Fix pre-TTS V17 over-trimming: 390-555 glyphs yielded observed 39s.
    # 430-700 glyphs more often lands in the 46-85s range and is still
    # constrained to previously visually evidenced beats, not invented narration.
    v17.MIN_CHARS = 430
    v17.MAX_CHARS = 700
    ns['APP_VERSION'] = VERSION
    ns['_V18_INSTALLED'] = True
    ns['app'].state.v18_short_voice_local_pacing = True
    @ns['app'].get('/api/v18/info')
    def info():
        return {'version': VERSION, 'target_seconds': 60,
                'short_narration_supported_seconds': [33, 46],
                'extra_gemini_calls': 0, 'voice_source': 'existing saved WAV',
                'pacing': 'quiet-gap editorial pauses and pitch-preserving atempo',
                'caveat': 'very short scripts still cannot be made into natural 60s narration'}
