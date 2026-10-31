"""V26: evidence-only, forward-only multi-take sentence editing.

A sentence can use multiple independently visually matched camera takes, with
continuous narration. Reject unsupported scenes and reject short final output.
No Gemini API calls are added, no source intervals are repeated.
"""
from __future__ import annotations
from functools import lru_cache
import math
import re

VERSION = 'v26-grounded-multishot-sentence-2026-10-31'
MAX_EXTENSION = 12.0
TARGET_FLOORS = {60: 420, 90: 625, 120: 830}


def glyphs(text):
    return len(re.sub(r'\s+', '', str(text or '')))


def _intervals(beat, shots, source_duration):
    """Only Gemini-approved shot IDs; extension remains inside *actual* camera take.

    The caller has already applied V14's per-beat score/evidence restrictions.
    We never import other scene IDs based solely on keywords or proximity.
    """
    lookup = {str(s['id']): s for s in shots}
    take_end = {}
    for s in shots:
        tid = str(s.get('take_id', 'isolated_' + str(s['id'])))
        take_end[tid] = max(take_end.get(tid, 0.), float(s['end']))
    identifiers = list(dict.fromkeys(str(x) for x in
        [beat.get('shot_id')] + list(beat.get('related_shots') or []) if x is not None))
    by_take = {}
    for sid in identifiers:
        s = lookup.get(sid)
        if not s:
            continue
        tid = str(s.get('take_id', 'isolated_' + str(s['id'])))
        start, end = float(s['start']), float(s['end'])
        if not (math.isfinite(start) and math.isfinite(end) and end > start):
            continue
        if tid in by_take:
            old = by_take[tid]
            by_take[tid] = (min(old[0], start), max(old[1], end), old[2], tid)
        else:
            by_take[tid] = (start, end, sid, tid)
    output = []
    for st, observed_end, sid, tid in by_take.values():
        end = min(float(source_duration), take_end[tid], observed_end + MAX_EXTENSION)
        if end - st >= .18:
            output.append((max(0., st), end, sid, tid))
    return sorted(output, key=lambda r: (r[0], r[1]))


def _cover(intervals, cursor, need, first_index):
    """Greedy forward allocation from ONE selected starting verified interval."""
    if first_index >= len(intervals):
        return None
    remaining = need
    now = max(cursor, intervals[first_index][0])
    cuts = []
    for j in range(first_index, len(intervals)):
        start, stop, sid, tid = intervals[j]
        at = max(start, now)
        available = stop - at
        if available <= .0001:
            continue
        take = min(available, remaining)
        if take <= .0001:
            continue
        cuts.append((at, take, sid, tid))
        remaining -= take
        now = at + take
        if remaining <= .0002:
            return tuple(cuts), now
    return None


def plan(beats, voice_duration, source_duration, shots, windows=None):
    """Find a chronological arrangement using only verified takes, even across real cuts."""
    import v22_scene as v22
    import v21_storyflow as v21
    if not beats or not math.isfinite(float(voice_duration)) or voice_duration <= 0:
        raise RuntimeError('ไม่มีเสียงหรือบทพูดที่ใช้ได้')
    if windows is None:
        windows = v21.phrase_windows(beats, voice_duration)
    if len(windows) != len(beats):
        raise ValueError('จำนวนช่วงเสียงไม่ตรงกับประโยค')
    choices = []
    for i, (beat, (vstart, vend)) in enumerate(zip(beats, windows)):
        needed = float(vend) - float(vstart)
        if not math.isfinite(needed) or needed < .2:
            raise v22.InsufficientFootage(i, 'ช่วงประโยคสั้นเกินไป')
        choices.append((needed, float(vstart), _intervals(beat, shots, source_duration)))
    deepest = [0]

    @lru_cache(maxsize=65000)
    def find(index, cursor):
        deepest[0] = max(deepest[0], index)
        if index == len(choices):
            return ()
        need, _, intervals = choices[index]
        for j, interval in enumerate(intervals):
            if interval[1] <= cursor + .001:
                continue
            covered = _cover(intervals, cursor, need, j)
            if covered is None:
                continue
            cuts, next_cursor = covered
            following = find(index + 1, round(next_cursor, 5))
            if following is not None:
                return (cuts,) + following
        return None

    allocation = find(0, 0.0)
    if allocation is None:
        idx = min(len(beats)-1, deepest[0])
        raise v22.InsufficientFootage(idx,
            'ภาพที่ยืนยันได้สำหรับประโยคนี้มีไม่พอ แม้รวมหลายช็อตที่เกี่ยวข้องแล้ว')

    output = []
    for beat, (_, vstart, _), sections in zip(beats, choices, allocation):
        local_voice = vstart
        for st, length, sid, tid in sections:
            done = 0.0
            while done < length - .000001:
                chunk = min(8.0, length - done)
                if 0 < length - done - chunk < .12:
                    chunk = length - done
                output.append({
                    'source_start': round(st + done, 5),
                    'duration': round(chunk, 5),
                    'voice_start': round(local_voice, 5),
                    'caption': beat.get('caption') or beat['narration'],
                    'text': beat['narration'], 'shot_id': sid,
                    'v26_independently_verified': True,
                    'v26_take_id': tid,
                })
                local_voice += chunk
                done += chunk
    if abs(sum(x['duration'] for x in output)-float(voice_duration)) > .08:
        raise RuntimeError('เสียงกับภาพไม่ครบตามระยะเวลา')
    if any(b['source_start'] < a['source_start'] + a['duration'] - .002
           for a, b in zip(output, output[1:])):
        raise RuntimeError('การจัดฉากย้อนภาพหรือใช้ซ้ำ')
    if any(b['voice_start'] < a['voice_start'] + a['duration'] - .002
           for a, b in zip(output, output[1:])):
        raise RuntimeError('เสียงพากย์ซ้อนกัน')
    return output


def preflight(result, shots, source_duration):
    """Keep a sufficient, evidence-supported story; an invalid first hook is droppable.

    V25 incorrectly rejected EVERY video if beat #1 exceeded a single take,
    even when enough later distinct verified footage supported >1 minute.
    """
    import v22_scene as v22
    beats = list(result.get('beats') or [])
    if not beats:
        return result
    selected = int(result.get('_v17_target_seconds') or 60)
    if selected not in TARGET_FLOORS:
        selected = 60
    floor = TARGET_FLOORS[selected]
    removed = []
    for _ in range(len(beats)):
        durations = [max(1.5, glyphs(b.get('narration'))/7.5) for b in beats]
        timestamp = 0.
        windows = []
        for seconds in durations:
            windows.append((timestamp, timestamp + seconds))
            timestamp += seconds
        try:
            planned = plan(beats, timestamp, source_duration, shots, windows)
            break
        except v22.InsufficientFootage as e:
            index = e.index
            surviving = [b for i, b in enumerate(beats) if i != index]
            # Drop any unallocatable *whole* sentence, including first hook,
            # only when plenty of independently supported content remains.
            if (not 0 <= index < len(beats) or len(surviving) < 5 or
                sum(glyphs(b.get('narration')) for b in surviving) < floor):
                raise RuntimeError(
                    f'ต้นฉบับยาว {float(source_duration):.1f} วินาที แต่บทพูดประโยคที่ {index + 1} '
                    'ไม่มีภาพที่ AI ยืนยันได้มากพอแม้ลองหลายช็อตแล้ว '
                    'และส่วนที่เหลือไม่พอสำหรับความยาวขั้นต่ำ — หยุดก่อนสร้างเสียง') from e
            removed.append({'index': index + 1, 'text': str(beats[index].get('narration',''))[:70]})
            beats = surviving
    else:
        raise RuntimeError('ไม่สามารถจับคู่บทกับภาพในต้นฉบับได้')

    if sum(glyphs(b.get('narration')) for b in beats) < floor:
        raise RuntimeError('บทที่ยืนยันภาพได้ยังสั้นเกินกว่าระยะเวลาที่เลือก — หยุดก่อนสร้างเสียง')
    result['beats'] = beats
    result['script'] = ' '.join(str(b['narration']) for b in beats)
    result['captions'] = [b.get('caption',b['narration']) for b in beats]
    result['highlights'] = [{'start': b['source_start'], 'end': b['source_end']}
                            for b in beats if 'source_start' in b and 'source_end' in b]
    result['v26_preflight'] = {
        'kept_beats': len(beats), 'removed_beats': len(removed),
        'removed_samples': removed[:3], 'verified_source_cuts': len(planned),
        'estimated_speech_seconds': round(sum(max(1.5, glyphs(b['narration']) / 7.5) for b in beats),1),
        'extra_gemini_calls': 0, 'no_repeat': True,
        'uses_independently_evidenced_multishot': True,
    }
    return result


def install(ns):
    if ns.get('_V26_INSTALLED'):
        return
    import v22_scene as v22
    import v25_adaptive as v25
    import v14_semantic as v14
    v25.plan = plan
    v25.preflight = preflight
    v22.plan = plan
    v22.preflight = preflight
    previous = v14.make_prompt
    def prompt(timecodes, length, tone):
        return previous(timecodes, length, tone) + (
            '\nV26 SHOT-BUDGET RULE: Write concise, complete Thai sentences that '
            'can be illustrated by several independently visually verified source '
            'shots, all in strictly increasing original timestamp order. Avoid '
            'long first hooks that a single shot cannot cover. Return explicit '
            'matching shot IDs for EACH beat in visual_matches; include additional '
            'IDs only if EACH has sufficient real visible evidence supporting the '
            'same sentence. Every beat should be about 3-6s natural speech. '
            'Keep the 60, 90, or 120 second total naturally, without filler or '
            'invented factual claims. Never link unrelated shots merely to add time.'
        )
    v14.make_prompt = prompt
    ns['APP_VERSION'] = VERSION
    ns['_V26_INSTALLED'] = True
    ns['app'].state.v26_multi_verified_takes = True
    ns['app'].state.v26_drops_unallocatable_first_beat_if_safe = True
    @ns['app'].get('/api/v26/info')
    def info():
        return {'version': VERSION, 'multi_take_per_sentence': True,
                'each_take_requires_independent_AI_visual_match': True,
                'forward_only': True, 'no_repeated_source_intervals': True,
                'first_beat_can_be_dropped_when_remaining_story_sufficient': True,
                'extra_gemini_calls': 0,
                'actual_duration_minimum_sec': 60}
