"""V28: truthful educational visual anchors and anonymized coverage diagnostics.

This module does not fabricate visual matches or downgrade their confidence scores.
Knowledge explanations may be illustrated by a relevant visible subject; scientific
claims still require independent grounding.  Errors expose aggregate evidence
coverage rather than only the first failed sentence.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

VERSION = 'v28-topic-grounded-visual-evidence-and-diagnostics-2026-10-31'
CONFIDENCE = 0.78


def coverage_report(analysis, shots):
    """Counts model-reported evidence; it cannot independently verify its truth."""
    if not isinstance(analysis, dict):
        analysis = {}
    lookup = {str(s.get('id')): s for s in shots if isinstance(s, dict) and 'id' in s}
    raw_scenes = analysis.get('scenes') or []
    scenes = {str(s['id']) for s in raw_scenes
              if isinstance(s, dict) and s.get('id') in lookup and
              isinstance(s.get('description'), str) and s['description'].strip()}
    eligible = set(map(str, analysis.get('_v14_candidate_shots') or lookup.keys()))
    supported = set()
    supported_beats = 0
    total_beats = 0
    for beat in analysis.get('beats') or []:
        if not isinstance(beat, dict):
            continue
        total_beats += 1
        current = set()
        for evidence in (beat.get('visual_matches') or [])[:8]:
            if not isinstance(evidence, dict):
                continue
            sid = str(evidence.get('id', ''))
            note = str(evidence.get('evidence') or '').strip()
            try:
                score = float(evidence.get('score', 0))
            except (TypeError, ValueError):
                continue
            if sid not in lookup or sid not in scenes or sid not in eligible:
                continue
            if not math.isfinite(score) or score < CONFIDENCE or score > 1 or len(note) < 8:
                continue
            current.add(sid)
        if current:
            supported_beats += 1
            supported.update(current)
    spans = []
    for sid in supported:
        s = lookup[sid]
        try:
            a, b = float(s['start']), float(s['end'])
        except (ValueError, TypeError, KeyError):
            continue
        if math.isfinite(a) and math.isfinite(b) and b > a:
            spans.append((a, b))
    spans.sort()
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    seconds = round(sum(b-a for a, b in merged), 1)
    return {'candidate_source_shots': len(lookup),
            'observed_scenes_described': len(scenes),
            'narration_beats': total_beats,
            'beats_with_model_evidence': supported_beats,
            'distinct_evidenced_shots': len(supported),
            'evidenced_partition_seconds': seconds,
            'threshold': CONFIDENCE,
            'note': 'Model-reported preliminary evidence; not independent verification or usable runtime'}


def error_note(report, raw_repair=None):
    """No scripts, private video information, API keys, or source URLs in user message."""
    good = report.get('beats_with_model_evidence', 0)
    total = report.get('narration_beats', 0)
    seconds = report.get('evidenced_partition_seconds', 0)
    msg = (f'AI จับคู่หลักฐานภาพเบื้องต้นได้ {good}/{total} ประโยค, '
           f'{report.get("distinct_evidenced_shots",0)} ช็อต, '
           f'ช่วงเวลาภาพต้นทางรวม {seconds:g} วินาที '
           '(ยังไม่ใช่เวลาภาพที่ตัดต่อได้จริง)')
    if raw_repair is not None:
        msg += (f'; รอบวางบทใหม่ {raw_repair.get("beats_with_model_evidence",0)}/'
                f'{raw_repair.get("narration_beats",0)} ประโยค, '
                f'{raw_repair.get("evidenced_partition_seconds",0):g} วินาที')
    return msg


def install(ns):
    if ns.get('_V28_INSTALLED'):
        return
    import v11
    import v14_semantic as v14
    import v27_replan as v27
    previous_prompt = v14.make_prompt

    def prompt(timecodes, length, tone):
        current = previous_prompt(timecodes, length, tone)
        if 'สาระน่ารู้' in str(tone):
            return current + (
                '\nFINAL V28 EDUCATIONAL VISUAL RULE: An externally supported fact '
                'can be ILLUSTRATED by footage clearly showing its distinctive real '
                'subject, even if the exact scientific mechanism itself is not visible. '
                'The script must distinguish what the camera shows from outside knowledge; '
                'do not assert unseen facts were filmed. For each 3-6 second Thai sentence, '
                'identify up to 8 distinct original shot IDs ONLY when they genuinely '
                'show that specific subject. Scores must be genuinely >= 0.78 with concrete '
                'visible evidence. No unrelated people or objects, no duplicate footage, '
                'and preserve increasing source time. If there is no suitable footage, '
                'refuse rather than fabricate.\n'
            )
        return current + (
            '\nFINAL V28 EVENT RULE: Keep visual evidence strict for actual reported '
            'actions. Prefer multiple independently verified chronological source shots '
            'that truly show the narrated event, with concise complete Thai sentences. '
            'Never invent footage or facts.\n'
        )

    v14.make_prompt = prompt
    previous_normalize = v11.normalize_beats

    def normalize(raw, shots, duration):
        try:
            return previous_normalize(raw, shots, duration)
        except RuntimeError as exc:
            context = v27._JOB.get()
            if context is None:
                raise
            folder = Path(ns['WORK']) / str(context['jid'])
            first = coverage_report(raw, shots)
            second = None
            cached = folder / 'analysis-replanned-v27.json'
            if cached.is_file():
                try:
                    second = coverage_report(json.loads(cached.read_text(encoding='utf-8')), shots)
                except (OSError, ValueError, TypeError):
                    pass
            audit = {'initial': first, 'replanned': second,
                     'source_duration_seconds': round(float(duration),1),
                     'target_seconds': int(context['opts'].get('length',60)),
                     'result': 'insufficient visually usable sequence; not an API outage'}
            # Private per-job metadata only: no full narration, source URL, or API key.
            v11.atom_json(folder / 'v28-visual-audit.json', audit)
            raise RuntimeError(str(exc)[:260] + ' | ตรวจภาพ: ' + error_note(first, second)) from exc

    v11.normalize_beats = normalize
    ns['_V28_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v28_educational_visual_anchors = True
    ns['app'].state.v28_visual_audit_without_api_key = True

    @ns['app'].get('/api/v28/info')
    def info():
        return {'version': VERSION,
                'knowledge_subject_illustration': True,
                'independent_factual_grounding_required': True,
                'visual_score_threshold': CONFIDENCE,
                'no_duplicate_or_unrelated_footage': True,
                'minimum_seconds': 60,
                'additional_gemini_requests': 0,
                'diagnostic_on_failure': 'aggregate model-reported visual coverage'}
