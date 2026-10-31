"""V29: prefer fresh evidenced source footage and preserve original audit input.

V14 source-selection previously preferred already-used shots due to an inverted
boolean sort. V28's error-report wrapper counted a normalization-mutated object
and misleadingly reported 0/X matches. Both are fixed by V29's installer.
"""
VERSION = 'v29-correct-verified-shot-selection-and-original-evidence-audit-2026-10-31'


def install(ns):
    if ns.get('_V29_INSTALLED'):
        return
    ns['_V29_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v29_fresh_supported_shot_first = True
    ns['app'].state.v29_raw_evidence_audit_preserved = True
    @ns['app'].get('/api/v29/info')
    def info():
        return {'version': VERSION,
                'prefer_new_verified_shots': True,
                'audit_uses_immutable_pre_normalization_evidence': True,
                'confidence_threshold_unchanged': 0.78,
                'minimum_output_seconds': 60,
                'no_extra_gemini_calls': True,
                'no_source_frame_replay': True}
