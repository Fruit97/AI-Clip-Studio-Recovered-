"""V32: recover the strongest ORIGINAL model evidence after a failed V27/V30 edit.

Only for externally sourced educational mode. Never manufacture visual matches,
search citations, source clips, voices, or timecodes. This is a fail-closed
recovery for prior visual planning errors, not a general exception suppressor.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

VERSION = 'v32-replanned-evidence-recovery-2026-11-01'
# V17 trims 60-second scripts to <=555 glyphs; V30 formerly required >=600.
# Keep a feasible pre-TTS overlap while the actual MP4 duration gate remains 60/90/120.
PREFLIGHT_GLYPH_FLOORS = {60:490, 90:705, 120:940}
VISUAL_FAILURE_START = (
    'ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว',
    'วิเคราะห์ภาพต้นฉบับเชิงลึกแล้ว',
    'ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที',
    'ภาพจริงที่ยืนยันได้มีช่วงเวลาไม่เพียงพอ',
    'ต้นฉบับยาว',
    'บทพูดที่มีหลักฐานภาพเหลือ',
    'บทที่ยืนยันภาพได้ยังสั้น',
    'ช่วงภาพ',
    'ภาพที่ยืนยัน',
    'ภาพต้นฉบับ',
    'ภาพประกอบตรงหัวข้อ',
    'โหมดภาพประกอบยังไม่ผ่าน',
)


def visual_planning_failure(error):
    """Message may *mention* 'TTS' or 'โควตา' when explaining it did not call TTS.

    Permit only named pre-TTS video/story coverage failures. A transport, voice,
    quota, JSON, FFmpeg or permission error must never be converted to fallback.
    """
    if not isinstance(error, RuntimeError):
        return False
    m = str(error).strip()
    low = m.casefold()
    disallow = ('gemini api (', '429', '503', 'ffmpeg:', 'gemini tts error',
                'quota exceeded', 'read timeout', 'api key', 'ไฟล์เสียงพากย์')
    if any(t in low for t in disallow):
        return False
    return any(m.startswith(prefix) for prefix in VISUAL_FAILURE_START)


def read_candidates(initial, folder):
    """Recover original, unmutilated Gemini JSON from THIS job's checkpoints.

    These files are written by v27 and v30 BEFORE their local normalization;
    don't promote model estimates into ground-truth guarantees.
    """
    yield 'initial', copy.deepcopy(initial)
    for name, filename in (
        ('replanned-v27', 'analysis-replanned-v27.json'),
        ('deep-v30', 'analysis-deep-v30.json'),
    ):
        p = Path(folder) / filename
        try:
            candidate = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get('beats'), list):
            yield name, candidate


def choose_recovery(initial, folder, shots, target, illustrator):
    """Try all 3 authentic model replies; prefer broader independently matched footage.

    Do NOT inject Google citations into a different model reply. Never guess
    missing scores, scenes, topic keywords, timestamp IDs, or source content.
    """
    import v28_alignment
    available = []
    diagnoses = []
    for name, candidate in read_candidates(initial, folder):
        try:
            report = v28_alignment.coverage_report(candidate, shots)
            outcome = illustrator(copy.deepcopy(candidate), shots, target)
            fb = outcome.get('v31_fallback') or {}
            used = int(fb.get('visually_verified_anchors', 0))
            beats = int(fb.get('accepted_facts', 0))
            chars = int(fb.get('spoken_characters', 0))
            if used < 1 or beats < 6 or chars < {60:600,90:900,120:1200}[target]:
                raise RuntimeError('บทความรู้หรือภาพรองรับความยาวไม่พอ')
            # More visibly evidenced moments is preferable to a single looped shot.
            quality = (int(report['distinct_evidenced_shots']),
                       int(report['beats_with_model_evidence']),
                       beats, chars)
            available.append((quality, name, outcome, report))
            diagnoses.append({'source':name, 'valid':True,
                              'model_evidenced_shots':report['distinct_evidenced_shots'],
                              'accepted_facts':beats})
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            # Do not record user text or model narration in persistent diagnostics.
            diagnoses.append({'source':name, 'valid':False,
                              'reason_type':type(e).__name__})
    if not available:
        return None, None, diagnoses
    quality, name, selected, report = max(available, key=lambda row:row[0])
    selected['v32_recovery'] = {
        'selected_source':name,
        'candidate_count':len(diagnoses),
        'evidenced_shots':report['distinct_evidenced_shots'],
        'evidenced_beats':report['beats_with_model_evidence'],
        'estimated_partition_seconds_not_usable_runtime':report['evidenced_partition_seconds'],
        'requires_real_source':True,
        'external_fact_citations_required':True,
        'model_evidence_not_ground_truth':True,
    }
    return name, selected, diagnoses


def install(ns):
    if ns.get('_V32_INSTALLED'):
        return
    import v11
    import v31_illustrative as v31
    import v30_source_first as v30
    before = v11.normalize_beats
    # A contradictory validation window could reject every STRICT 60s script:
    # V17 MAX_CHARS=555 vs old V30 minimum 600. This does not change
    # output duration, voice speed, source-footage or exact-frame checks.
    v30.TARGETS.update(PREFLIGHT_GLYPH_FLOORS)

    def normalize(raw, shots, source_duration):
        original = copy.deepcopy(raw)
        try:
            result = before(raw, shots, source_duration)
        except RuntimeError as error:
            if not visual_planning_failure(error):
                raise
            context = v30._JOB.get()
            if not isinstance(context,dict):
                raise
            opts = context.get('opts') or {}
            if 'สาระน่ารู้' not in str(opts.get('tone','')):
                raise
            target = int(opts.get('length',60))
            if target not in (60,90,120):
                raise
            folder = Path(ns['WORK']) / str(context['jid'])
            source, recovered, report = choose_recovery(original, folder, shots, target,
                                                        v31.make_illustrative)
            if recovered is None:
                # Failure remains visible and no TTS is called. Only aggregates saved.
                v11.atom_json(folder/'v32-source-selection.json', {
                    'status':'insufficient_relevant_verified_footage',
                    'target':target,'candidates':report})
                raise RuntimeError(
                    'ตรวจภาพและบทครบทั้งรอบแรก รอบวางบทใหม่ และรอบลึกแล้ว แต่ยังไม่มี '
                    'ภาพที่ตรงหัวข้อพร้อมแหล่งอ้างอิงพอสร้างคลิปตามความยาวที่เลือก '
                    'ระบบหยุดก่อนเรียกเสียงเพื่อไม่เสียโควตา') from error
            v11.atom_json(folder/'v32-source-selection.json', {
                'status':'selected','target':target,'chosen':source,'candidates':report,
                'model_verification_is_not_independent':True,
            })
            ns['notify'](context['jid'],43,
                         'เลือกเนื้อหาและช็อตจากผลวิเคราะห์ต้นฉบับที่ตรวจได้ดีที่สุด')
            return recovered
        # V31 can succeed with 3 early anchors even when V27 supplied
        # 12 independent matches. Prefer richer original footage when both
        # answers are valid, with no additional API call.
        if isinstance(result,dict) and result.get('v31_fallback'):
            ctx=v30._JOB.get()
            if isinstance(ctx,dict) and 'สาระน่ารู้' in str((ctx.get('opts') or {}).get('tone','')):
                target=int(ctx['opts'].get('length',60))
                if target in (60,90,120):
                    folder=Path(ns['WORK'])/str(ctx['jid'])
                    name,choice,diagnostics=choose_recovery(original,folder,shots,target,
                                                              v31.make_illustrative)
                    prior=int(result.get('v31_fallback',{}).get('visually_verified_anchors',0))
                    if choice is not None and choice['v32_recovery']['evidenced_shots']>prior:
                        v11.atom_json(folder/'v32-source-selection.json', {
                            'status':'selected','target':target,'chosen':name,
                            'candidates':diagnostics,'model_verification_is_not_independent':True})
                        ns['notify'](ctx['jid'],43,'เลือกฉากที่ยืนยันได้มากที่สุดจากผลวิเคราะห์ต้นฉบับ')
                        return choice
        return result

    v11.normalize_beats = normalize
    ns['_V32_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v32_visual_replan_recovery = True
    @ns['app'].get('/api/v32/info')
    def info():
        return {'version':VERSION,'scope':'grounded educational illustration only',
                'candidate_sources':['initial','replanned-v27','deep-v30'],
                'no_additional_gemini_calls':True,
                'minimum_evidence_score':.78,
                'compatible_tts_glyph_floors':PREFLIGHT_GLYPH_FLOORS,
                'no_external_images':True,
                'raw_model_evidence_is_not_guaranteed':True}
