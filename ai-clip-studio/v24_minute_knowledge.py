"""AI Clip Studio V24: 60-second minimum, knowledge mode and verified sources.

This release refuses short, repetitive or unsourced knowledge videos instead of
manufacturing footage, stretching narration or silently reducing the requested
minimum. External facts are allowed only if Gemini returns Google Search grounding.
"""
from __future__ import annotations
import contextvars
import json
import math
from pathlib import Path
import re

VERSION = 'v24-knowledge-minimum-one-minute-2026-10-31'
DURATIONS = (60, 90, 120)
_CURRENT = contextvars.ContextVar('v24_job', default=None)


def is_knowledge(tone):
    return 'สาระน่ารู้' in str(tone)


def check_length(length):
    try:
        number = int(length)
    except (TypeError, ValueError):
        raise ValueError('เลือกความยาว 60, 90 หรือ 120 วินาทีเท่านั้น')
    if number not in DURATIONS:
        raise ValueError('คลิปทุกโหมดต้องยาวอย่างน้อย 1 นาที กรุณาเลือก 60, 90 หรือ 120 วินาที')
    return number


def evidence_sources(response):
    """Use grounded URLs only; never accept model-composed URL strings."""
    candidates = response.get('candidates') or []
    meta = candidates[0].get('groundingMetadata') or {} if candidates else {}
    sources = []
    for item in (meta.get('groundingChunks') or []):
        web = item.get('web') if isinstance(item, dict) else None
        if not isinstance(web, dict):
            continue
        url = str(web.get('uri') or '').strip()
        if not re.match(r'^https://[^\s]+$', url, re.I):
            continue
        title = str(web.get('title') or 'แหล่งข้อมูลอ้างอิง')[:120]
        if url not in [x['url'] for x in sources]:
            sources.append({'title': title, 'url': url})
    return sources[:12]


def duration_prompt(existing, seconds):
    """Override legacy 60s-only guidance for every selectable longer format."""
    seconds = check_length(seconds)
    suggested = {60: '11-16', 90: '16-22', 120: '19-28'}[seconds]
    return existing + (
        '\nFINAL DURATION CONTRACT FOR ALL MODES: target at least '
        f'{seconds} seconds of fluent natural Thai speech. Use about '
        f'{suggested} distinct fact-rich complete narration beats if footage supports them. '
        'The earlier fixed 11-16 beat preference applies ONLY to a 60-second '
        'video, never to 90- or 120-second videos. Do not shorten the video '
        'to 10, 15, 20, 30 or 55 seconds. Never repeat footage, introduce '
        'fake facts, stretch spoken words or insert long filler pauses. If '
        'source evidence is inadequate, the system rejects the job instead '
        'of claiming it can deliver a longer documentary from insufficient footage.'
    )


def knowledge_prompt(existing, tone, seconds):
    if not is_knowledge(tone):
        return existing
    return existing + (
        '\nKNOWLEDGE MODE OVERRIDES THE EDITORIAL FORMAT: Write an engaging Thai educational '
        'video, not merely a play-by-play video description. Open with an accurate, specific '
        'question or curiosity hook about a subject actually visible in the uploaded footage. '
        'Explain WHY, HOW, or a surprising verified factual mechanism, then practical context '
        'and an intelligent conclusion. Only present outside facts that were corroborated '
        'by Google Search grounding in this request. Never make unsupported health, science, '
        'historical or statistical claims; never pretend a mechanism is visibly filmed when '
        'only the animal/object in question is shown. Differentiate "the video shows" from '
        '"scientists know". Anchor EACH narration beat to a truly visible relevant subject '
        'and an unbroken illustrative original video shot, not a staged illustration of an '
        'unseen fact. A shot of a cat grooming CAN illustrate a verified explanation of cat '
        'tongue anatomy without claiming that microscopic papillae are shown in the shot. '
        'Visual evidence must certify subject identity and on-screen action; web evidence '
        'must certify the offscreen educational assertion. Avoid filler, repeated sentences, '
        'fake urgency and made-up numbers. Include at least 2 substantial educational '
        'takeaways with grounded facts, and ensure every beat forms a complete natural Thai '
        'sentence. Respect chronology and original footage without repeating frames. '
        f'Target {int(seconds)} to {int(seconds)+8} seconds of natural Thai narration, '
        'but do not slow down delivery to fill the target. Return the existing JSON shape '
        'including per-beat visual_matches and scene IDs; do not fabricate source URLs.'
    )


def footage_gate(source_seconds, target):
    target = check_length(target)
    if not math.isfinite(float(source_seconds)) or float(source_seconds) + 0.08 < target:
        raise ValueError(
            f'วิดีโอต้นฉบับมีภาพต่อเนื่องประมาณ {float(source_seconds):.1f} วินาที '
            f'แต่เลือกคลิป {target} วินาที ต้องมีภาพต้นฉบับอย่างน้อย {target} วินาที '
            'เพื่อไม่ย้อนฉากหรือวนภาพเดิม กรุณาเลือกวิดีโอต้นฉบับที่ยาวกว่า'
        )
    return target


def output_gate(seconds, target):
    target = check_length(target)
    if not math.isfinite(float(seconds)) or float(seconds) + 1.e-3 < target:
        raise ValueError(
            f'ไฟล์ที่เรนเดอร์มีความยาว {float(seconds):.2f} วินาที '
            f'ซึ่งต่ำกว่าระยะที่เลือก {target} วินาที ระบบไม่ส่งออกคลิปที่สั้นกว่า '
            'ไม่ยืดเสียง ไม่แทรกภาพค้าง และไม่วนฉากเดิมเพื่อเพิ่มเวลา'
        )
    return True


def install(ns):
    if ns.get('_V24_MINUTE_INSTALLED'):
        return
    import v11
    import v14_semantic as v14

    previous_prompt = v14.make_prompt
    def prompted(timecodes, length, tone):
        return knowledge_prompt(duration_prompt(previous_prompt(timecodes, length, tone), length), tone, length)
    v14.make_prompt = prompted

    prior_process = ns['process']
    def process(jid, src_path, link, key, opts):
        token = _CURRENT.set(jid)
        try:
            selected = check_length(opts.get('length', 60))
            if src_path:
                source = Path(src_path)
                if source.exists():
                    seconds, _ = ns['probe'](source)
                    footage_gate(seconds, selected)
            prior_process(jid, src_path, link, key, opts)
            # The 60s check also applies after the older pipeline has finished.
            with ns['lock']:
                job = ns['jobs'].get(jid)
                if not job or job.get('state') != 'done':
                    return
                result = ns['WORK'] / jid / 'result.mp4'
                output_gate(v11.duration_of(result), selected)
                if is_knowledge(opts.get('tone')):
                    analysis_file = ns['WORK'] / jid / 'analysis-v11.json'
                    analysis = json.loads(analysis_file.read_text('utf-8'))
                    sources = analysis.get('knowledge_sources') or []
                    if not sources:
                        raise ValueError('โหมดสาระน่ารู้ไม่มีแหล่งอ้างอิงจาก Google Search จึงไม่สามารถส่งออกความรู้ที่ยังไม่ได้ตรวจสอบ')
                    job['knowledge_sources'] = sources
                    job['mode_note'] = 'สาระน่ารู้: เพิ่มข้อเท็จจริงที่อ้างอิงจาก Google Search พร้อมภาพต้นฉบับจริง'
                job['selected_min_seconds'] = selected
                ns['save_job'](jid)
        except Exception as exc:
            with ns['lock']:
                job = ns['jobs'].get(jid)
                if job:
                    clean = str(exc).replace(str(key or ''), '[redacted]') if key else str(exc)
                    job.update(state='error', error=clean[:650], step='ตรวจสอบคลิปขั้นต่ำหนึ่งนาที', progress=min(job.get('progress',0),99))
                    ns['save_job'](jid)
        finally:
            _CURRENT.reset(token)

    ns['process'] = process
    ns['_V24_MINUTE_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v24_min_duration_seconds = 60
    ns['app'].state.v24_duration_options = DURATIONS
    ns['app'].state.v24_knowledge_grounding = 'googleSearch required'

    @ns['app'].get('/api/v24/info')
    def info():
        return {'version': VERSION, 'duration_options': list(DURATIONS),
                'minimum_output_seconds': 60, 'knowledge_mode': True,
                'knowledge_grounding_required': True,
                'no_repeated_footage_or_slow_voice_padding': True,
                'limitations': 'Needs original footage at least as long as selected duration and Gemini Google Search grounding; output below target is rejected'}
