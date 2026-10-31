"""V21: information-first Thai story, natural narration and chronological no-repeat cuts.

A 60s selection remains a *target*. If the single TTS response is shorter,
export its natural length instead of stretching speech, repeating footage or
making a freeze-frame. No extra Gemini API request is made for pacing.
"""
from __future__ import annotations
import contextvars
import math
import os
from pathlib import Path
import re
import wave

VERSION = 'v21-storyflow-natural-voice-2026-10-31'
_ACTIVE = contextvars.ContextVar('v21_active', default=False)
_RENDER = contextvars.ContextVar('v21_render', default=None)


def editorial_prompt(original, timecodes, length, tone):
    return original(timecodes, length, tone) + (
        '\nEDITORIAL RULES, MANDATORY: First identify the ONE central idea of the actual video: '
        'what it is about, what happens, what viewers should understand, and why it matters. '
        'The title must say the specific subject rather than generic "important news". Within the FIRST spoken Thai sentence, clearly say what this video is about and the concrete event or topic; then deliver an intriguing specific hook. '
        'The summary must be 2-3 concrete, verifiable Thai sentences explaining the main point. '
        'Start narration with one engaging, truthful, concise hook (no clickbait, fabricated stakes, '
        'numbers, names or claims). Follow with 2-4 clearly supported takeaways or actual events, '
        'then a meaningful conclusion. Tell the STORY, not a list of "here is an image" or '
        '"now we see" descriptions. Give concrete relevant information for people who watch. '
        'Do not pad with generic praise or a repetitive introduction. Every beat must be a COMPLETE '
        'short Thai sentence or sentence-group about one meaningful fact, action or development; '
        'avoid fragmented pauses. Put beats in CHRONOLOGICAL SOURCE TIMESTAMP order, and anchor '
        'each entire sentence to one continuous, sufficiently long, verified original shot whenever possible. '
        'A related shot may be used only with video evidence that explicitly supports that sentence. '
        'Do not revisit previously used source moments, loop footage, or jump backward to the same scene. '
        'Prefer 11-16 substantive beats, approximately 3-6 seconds each at NATURAL conversational Thai speed. '
        'Do not produce empty filler to force exactly 60 seconds. '
        'The selected duration is a target, not license to slow speech or repeat footage. '
        'If the source has fewer facts, write fewer strong sentences and preserve accuracy. '
        'Output exactly the existing JSON fields; do not add a second model request.'
    )


def polish_story(result):
    """Keep only grounded beats, order once by source time, avoid narration duplicates."""
    beats = list(result.get('beats') or [])
    if not beats:
        return result
    # Evidence comes from V14. Never invent words or footage at this layer.
    beats.sort(key=lambda b: (float(b.get('source_start', 0)), float(b.get('source_end', 0))))
    unique = []
    seen = set()
    for beat in beats:
        content = re.sub(r'\s+', '', str(beat.get('narration', '')).casefold())
        # Exact duplicate narration is filler and cannot help narrative flow.
        if not content or content in seen:
            continue
        seen.add(content)
        unique.append(beat)
    if len(unique) < 2 and len(beats) >= 2:
        # Do not silently remove the whole story from an underspecified model output.
        raise RuntimeError('AI ส่งบทซ้ำมากเกินไป ไม่สร้างเสียงพากย์ซ้ำจนเสียโควตา')
    if len(unique) < 2:
        # One meaningful scene can still make a brief, honest video.
        unique = beats[:1]
    # Pre-TTS guard: one short source shot repeated in different narration beats
    # cannot make an engaging minute. Refuse before using a second Gemini TTS call.
    pools=[]
    for beat in unique:
        if 'source_start' in beat and 'source_end' in beat:
            a=float(beat['source_start']); b=float(beat['source_end'])
            if b>a: pools.append((a,b))
    merged=[]
    for a,b in sorted(pools):
        if merged and a<=merged[-1][1]+.002:
            merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else: merged.append((a,b))
    supported=sum(b-a for a,b in merged)
    minimum=min(30.,max(10.,len(unique)*2.5))
    if pools and supported < minimum:
        raise RuntimeError('ภาพจริงที่ยืนยันได้มีช่วงเวลาไม่เพียงพอต่อการเล่าเรื่องต่อเนื่อง '
                           'หยุดก่อนเรียก Gemini TTS เพื่อรักษาโควตา; '
                           'กรุณาเลือกวิดีโอที่มีเหตุการณ์หลายช่วงมากขึ้น')
    result['beats'] = unique
    result['script'] = ' '.join(str(b['narration']) for b in unique)
    result['captions'] = [b.get('caption', b['narration']) for b in unique]
    result['highlights'] = [
        {'start': b['source_start'], 'end': b['source_end']}
        for b in unique if 'source_start' in b and 'source_end' in b
    ]
    if isinstance(result.get('visual_matching_report'), dict):
        result['visual_matching_report']['accepted'] = len(unique)
    result['v21_story'] = {'main_topic': result.get('title', ''),
                           'summary': result.get('summary', ''),
                           'ordered_source_beats': len(unique),
                           'avoided_identical_narrations': len(beats) - len(unique)}
    return result


def natural_voice(path, legacy):
    """Never modify TTS audio in V21. Keep a speaker's original tempo."""
    if not _ACTIVE.get():
        return legacy(path)
    import v11
    seconds = v11.duration_of(path)
    if not (5 <= seconds <= 180) or not math.isfinite(seconds):
        raise RuntimeError('Gemini ส่งเสียงพากย์ที่ใช้ไม่ได้ กรุณาตรวจต้นฉบับเสียง')
    return seconds


def phrase_windows(beats, duration, wav=None):
    """Use detected real quiet breaks near predicted end-of-sentence times."""
    if not beats or duration <= 0:
        raise RuntimeError('ไม่มีข้อความหรือเสียงสำหรับจัดฉาก')
    weights = [max(5, len(re.sub(r'\s+', '', str(b['narration'])))) for b in beats]
    total = sum(weights)
    pauses = []
    if wav and Path(wav).exists():
        try:
            import v18_voice
            pauses = v18_voice._quiet_pause_times(wav)
        except (OSError, ValueError):
            pass
    selected = [0.]
    cumulative = 0
    for i, weight in enumerate(weights[:-1]):
        cumulative += weight
        expected = duration * cumulative / total
        # Do not force a cut into the middle of a spoken sentence when a real
        # pause is close. Cap maximum adjustment to avoid wildly wrong matches.
        proximity = min(1.6, max(.45, duration / len(beats) * .3))
        options = [p for p in pauses if abs(p - expected) <= proximity
                   and p > selected[-1] + .65]
        bound = min(options, key=lambda p: abs(p - expected)) if options else expected
        if bound <= selected[-1] + .15:
            bound = selected[-1] + .15
        selected.append(bound)
    selected.append(duration)
    return [(selected[i], selected[i + 1]) for i in range(len(beats))]


def sequential_shots(beats, voice_duration, source_duration, shots, wav=None):
    """Each sentence gets a forward-going real shot. Never repeat a video time range."""
    if not beats or voice_duration <= 0 or source_duration <= 0:
        raise RuntimeError('ไม่มีข้อมูลภาพหรือเสียงเพียงพอสำหรับตัดต่อ')
    lookup = {str(s['id']): s for s in shots}
    cuts = []
    cursor = -0.001
    windows = phrase_windows(beats, voice_duration, wav)
    for beat, (start_voice, end_voice) in zip(beats, windows):
        needed = end_voice - start_voice
        if needed < .2:
            raise RuntimeError('บทพูดสั้นเกินไปสำหรับเปลี่ยนฉากตามประโยค')
        ids = [str(beat.get('shot_id', ''))] + [str(s) for s in beat.get('related_shots', [])]
        choices = sorted((lookup[sid] for sid in dict.fromkeys(ids) if sid in lookup),
                         key=lambda s: float(s['start']))
        # A single continuous shot per narration beat avoids mid-sentence jump cuts.
        candidates=[]
        for s in choices:
            a = max(float(s['start']), cursor)
            z = min(float(s['end']), source_duration)
            if z - a + 1e-6 >= needed:
                candidates.append((a, z, s))
        if not candidates:
            raise RuntimeError(
                'ภาพที่ AI ยืนยันว่าตรงกับประโยคมีความยาวต่อเนื่องไม่พอ '
                'ระบบจะไม่วนกลับฉากเดิมหรือสลับภาพสะดุดเพื่อถมเวลา '
                'กรุณาเลือกคลิปที่มีภาพประกอบประเด็นครบขึ้น')
        a, z, chosen = candidates[0]
        # Longer scenes remain the same shot; only *encoding* chunks are split.
        remaining, source_at, voice_at = needed, a, start_voice
        while remaining > 0.0001:
            take = min(8.0, remaining)
            if remaining - take < .12: take = remaining
            cuts.append({'source_start': round(source_at, 4),
                         'duration': round(take, 4),
                         'voice_start': round(voice_at, 4),
                         'caption': beat.get('caption', beat['narration']),
                         'text': beat['narration'], 'shot_id': chosen['id'],
                         'v21_forward_only': True})
            source_at += take
            voice_at += take
            remaining -= take
        cursor = a + needed
    if abs(sum(s['duration'] for s in cuts) - voice_duration) > .12:
        raise RuntimeError('เสียงกับภาพคลาดเคลื่อนระหว่างสร้างไทม์ไลน์')
    return cuts


def write_silence(path, duration, sample_rate=24000):
    """Small reused WAV per job so segment mux never chops narration itself."""
    frames = math.ceil((duration + 1.0) * sample_rate)
    with wave.open(str(path), 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        block = b'\0' * 2 * 8192
        while frames:
            n = min(8192, frames)
            writer.writeframesraw(block[:2 * n])
            frames -= n
        writer.writeframes(b'')


def mux_continuous_voice(raw, final, voice, expected_duration):
    """One uninterrupted narration track, with optional original ambient underneath."""
    import v11
    raw, final, voice = Path(raw), Path(final), Path(voice)
    if not v11.media_ok(raw, max(1, expected_duration - 2)):
        raise RuntimeError('ไฟล์ตัดต่อวิดีโอยังไม่สมบูรณ์')
    tmp = final.with_name('v21_final.tmp.mp4')
    if tmp.exists(): tmp.unlink()
    # Each rendered scene contains quiet ambience, NOT chopped narration.
    v11.ffmpeg_run(['-i',str(raw),'-i',str(voice),
       '-filter_complex','[0:a:0][1:a:0]amix=inputs=2:duration=first:dropout_transition=0,'
                         'aresample=async=1:first_pts=0,alimiter=limit=0.95[a]',
       '-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','128k',
       '-ar','48000','-ac','2','-t',f'{expected_duration:.5f}',
       '-movflags','+faststart',str(tmp)],timeout=240)
    observed = v11.duration_of(tmp)
    if abs(observed - expected_duration) > .18 or not v11.media_ok(tmp, expected_duration - .2):
        raise RuntimeError('ไฟล์วิดีโอที่ผสมเสียงต่อเนื่องมีระยะเวลาผิดปกติ')
    tmp.replace(final)
    return final


def install(ns):
    if ns.get('_V21_INSTALLED'): return
    import v11
    import v14_semantic as v14
    import v15_60seconds as v15
    old_prompt = v14.make_prompt
    v14.make_prompt = lambda tc, length, tone: editorial_prompt(old_prompt, tc, length, tone)
    old_normalize = v11.normalize_beats
    v11.normalize_beats = lambda raw, shots, length: (
        polish_story(old_normalize(raw, shots, length)) if _ACTIVE.get()
        else old_normalize(raw, shots, length))
    old_beats = v11.time_beats
    def time_beats(beats, duration, source_duration, shots):
        if not _ACTIVE.get():
            return old_beats(beats, duration, source_duration, shots)
        context = _RENDER.get() or {}
        return sequential_shots(beats, duration, source_duration, shots, context.get('voice'))
    v11.time_beats = time_beats
    old_ensure = v15.ensure_voice_60
    v15.ensure_voice_60 = lambda wav: natural_voice(wav, old_ensure)
    original_render_one = v11.render_one
    def render_one(source, voice, dest, ass, segment, has_audio, keep_sound):
        context = _RENDER.get()
        if context and _ACTIVE.get():
            return original_render_one(source, context['silence'], dest, ass,
                                       segment, has_audio, keep_sound)
        return original_render_one(source, voice, dest, ass, segment, has_audio, keep_sound)
    v11.render_one = render_one
    previous_finalize = v15.finalize_mp4_60
    def finalize(raw, final):
        context = _RENDER.get()
        if not (context and _ACTIVE.get()):
            return previous_finalize(raw, final)
        return mux_continuous_voice(raw, final, context['voice'], context['seconds'])
    v15.finalize_mp4_60 = finalize
    previous_timeline = v11.render_timeline
    def render_timeline(ns1,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots):
        if not _ACTIVE.get() or int(opts.get('length',30)) != 60:
            return previous_timeline(ns1,jid,source,voice,folder,beats,source_duration,
                                     source_audio,voice_duration,opts,shots)
        folder=Path(folder)
        # Old caches may contain loops and already slowed voice. Do not reuse the
        # looped video; preserve original source, raw Gemini analysis and TTS.
        if not (folder/'v21_success.marker').exists():
            for pattern in ('timeline-v11.json','v11_part_*.mp4','v11_combined.tmp.mp4',
                            'v15_raw_edit.mp4','result.mp4'):
                for item in folder.glob(pattern): item.unlink(missing_ok=True)
        silence=folder/'v21_silence.wav'
        if not silence.exists() or v11.duration_of(silence) < voice_duration + .1:
            write_silence(silence, voice_duration)
        token=_RENDER.set({'voice':Path(voice),'silence':silence,'seconds':voice_duration})
        try:
            result = previous_timeline(ns1,jid,source,voice,folder,beats,source_duration,
                                       source_audio,voice_duration,opts,shots)
            (folder/'v21_success.marker').write_text(VERSION,encoding='utf-8')
            return result
        finally:
            _RENDER.reset(token)
    v11.render_timeline=render_timeline
    previous_process=ns['process']
    def process(jid,src_path,link,key,opts):
        active=bool(opts.get('editorial_v21', True)) and int(opts.get('length',30))==60
        t=_ACTIVE.set(active)
        try:
            return previous_process(jid,src_path,link,key,opts)
        finally:
            _ACTIVE.reset(t)
    ns['process']=process
    ns['_V21_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v21_natural_speech=True
    ns['app'].state.v21_chronological_no_repeat=True
    @ns['app'].get('/api/v21/info')
    def info():
        return {'version': VERSION, 'main_idea_hook_takeaways_conclusion':True,
                'natural_tts_speed': True, 'repeat_video':False,
                'sentence_aligned_cuts':'acoustic quiet-gap assisted; approximate',
                'continuous_voice_audio':True, 'extra_gemini_requests':0,
                'duration':'60s target; natural shorter/longer permitted instead of stretching'}
