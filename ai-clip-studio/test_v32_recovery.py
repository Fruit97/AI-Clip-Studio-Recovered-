"""V32 tests based on the 412.5-second / 4-of-5 vs 12-of-12 regression.

The archived model JSON remains synthetic; no use of paid Gemini APIs.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
import pytest
import v32_recovery as v32


@pytest.mark.parametrize('msg', [
    'ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว แต่ยังมีช่วงภาพที่ไม่รองรับ และระบบไม่เรียก TTS เพื่อป้องกันเสียโควตา',
    'ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที ไม่เรียก TTS เพื่อป้องกันเสียโควตา',
    'วิเคราะห์ภาพต้นฉบับเชิงลึกแล้ว แต่โหมด 60 ยังมีภาพ/เนื้อหาที่ตรวจยืนยันไม่ครบ',
    'บทที่ยืนยันภาพได้ยังสั้นเกินกว่าระยะเวลาที่เลือก',
])
def test_visual_refusal_even_with_quota_word(msg):
    assert v32.visual_planning_failure(RuntimeError(msg))


@pytest.mark.parametrize('msg', [
    'Gemini API (429): quota exceeded',
    'Gemini API (503): service overloaded',
    'FFmpeg: corrupted encoding',
    'Gemini TTS error: voice blocked',
    'ภาพต้นฉบับขัดข้อง: Gemini API (429)',
    'read timeout',
])
def test_does_not_hide_actual_external_errors(msg):
    assert not v32.visual_planning_failure(RuntimeError(msg))


def _raw(shots, length=12, direct=12, cite=True):
    anchor={'id':'', 'score':.94,'evidence':'เสือโคร่งเดินอยู่ในป่าต้นไม้สูงในฉากจริง'}
    word='เสือโคร่งกำลังใช้ชีวิตอยู่ตามธรรมชาติ ข้อมูลที่กล่าวถึงอ้างอิงแหล่งความรู้ที่ตรวจสอบได้ '
    beats=[]
    for i in range(length):
        match=dict(anchor,id=shots[i%len(shots)]['id'])
        beats.append({'narration':word+f'ข้อที่ {i+1} เป็นเรื่องน่ารู้',
                      'visual_keywords':['เสือโคร่ง'],'shot_id':match['id'],
                      'caption':'ความรู้เสือโคร่ง','visual_matches':[match] if i<direct else []})
    d={'_v14_evidence_required':True,'_v14_candidate_shots':[x['id'] for x in shots],
       'beats':beats,'scenes':[{'id':x['id'],'description':'เสือโคร่งเดินอยู่ในป่าต้นไม้สูง',
                               'tags':['เสือโคร่ง','ป่า']} for x in shots]}
    if cite:d['knowledge_sources']=[{'url':'https://example.org/research','title':'Source'}]
    return d


def coverage_report(raw,shots):
    unique={m['id'] for b in raw['beats'] for m in b.get('visual_matches',[]) if m['score']>=.78}
    return {'distinct_evidenced_shots':len(unique),
            'beats_with_model_evidence':sum(bool(b['visual_matches']) for b in raw['beats']),
            'evidenced_partition_seconds':len(unique)*5.97}


def test_replanned_12_of_12_beats_wins_over_4_of_5(tmp_path,monkeypatch):
    import v31_illustrative as v31
    fake=ModuleType('v28_alignment')
    fake.coverage_report=coverage_report
    monkeypatch.setitem(sys.modules,'v28_alignment',fake)
    shots=[{'id':f's{i:03}','start':i*5.97,'end':(i+1)*5.97} for i in range(70)]
    original=_raw(shots[:5],length=5,direct=4)
    repaired=_raw(shots[:12],length=12,direct=12)
    (tmp_path/'analysis-replanned-v27.json').write_text(json.dumps(repaired,ensure_ascii=False),'utf8')
    name,chosen,report=v32.choose_recovery(original,tmp_path,shots,60,v31.make_illustrative)
    assert name=='replanned-v27'
    assert chosen['v32_recovery']['evidenced_shots']==12
    assert chosen['v31_fallback']['accepted_facts']>=6
    assert chosen['v32_recovery']['estimated_partition_seconds_not_usable_runtime']>70
    assert len(report)==2 and not report[0]['valid'] and report[1]['valid']
    assert all(x['caption'].startswith('ภาพประกอบ') for x in chosen['beats'])
    assert all(x['_v31_illustrative'] for x in chosen['beats'])


def test_no_grounding_no_salvage(tmp_path,monkeypatch):
    import v31_illustrative as v31
    fake=ModuleType('v28_alignment');fake.coverage_report=coverage_report
    monkeypatch.setitem(sys.modules,'v28_alignment',fake)
    shots=[{'id':f's{i:03}','start':i*6.,'end':(i+1)*6.} for i in range(15)]
    no_citations=_raw(shots,length=12,cite=False)
    name,recovered,reports=v32.choose_recovery(no_citations,tmp_path,shots,60,v31.make_illustrative)
    assert name is None and recovered is None
    assert reports[0]['valid'] is False


def test_no_gemini_or_tts_retry_and_prevent_other_modes(tmp_path,monkeypatch):
    from fastapi import FastAPI
    import v11,v30_source_first as v30
    path=tmp_path/'jobno';path.mkdir()
    shots=[{'id':f's{i:03}','start':i*6,'end':(i+1)*6} for i in range(12)]
    repaired=_raw(shots,length=12)
    (path/'analysis-replanned-v27.json').write_text(json.dumps(repaired,ensure_ascii=False),'utf8')
    def old(*args):raise RuntimeError('ลองวางบทจากภาพจริงอีกหนึ่งรอบแล้ว แต่ยังมีช่วงภาพที่ไม่รองรับ และระบบไม่เรียก TTS เพื่อป้องกันเสียโควตา')
    monkeypatch.setattr(v11,'normalize_beats',old)
    token=v30._JOB.set({'jid':'jobno','opts':{'length':60,'tone':'สาระน่ารู้'}})
    fired=[]
    ns={'app':FastAPI(),'WORK':tmp_path,'notify':lambda *args:fired.append(args)}
    v32.install(ns)
    out=v11.normalize_beats(_raw(shots[:5],length=5,direct=4),shots,412.5)
    assert out['v32_recovery']['selected_source']=='replanned-v27'
    assert len(fired)==1
    assert (path/'v32-source-selection.json').is_file()
    assert ns['app'].state.v32_visual_replan_recovery
    # Switch the context to an event-news mode with no independent citations.
    v30._JOB.reset(token)
    token2=v30._JOB.set({'jid':'jobno','opts':{'length':60,'tone':'ข่าวและสาระ'}})
    try:
        with pytest.raises(RuntimeError,match='ลองวางบท'):
            v11.normalize_beats(_raw(shots[:5],length=5,direct=4),shots,412.5)
    finally:
        v30._JOB.reset(token2)


def test_no_context_no_recovery(tmp_path,monkeypatch):
    from fastapi import FastAPI
    import v11,v30_source_first as v30
    monkeypatch.setattr(v11,'normalize_beats',lambda *args: (_ for _ in ()).throw(RuntimeError('ภาพที่เกี่ยวข้องให้เนื้อหาไม่พอสำหรับคลิปหนึ่งนาที')))
    token=v30._JOB.set(None)
    ns={'app':FastAPI(),'WORK':tmp_path,'notify':lambda *args:None}
    v32.install(ns)
    try:
        with pytest.raises(RuntimeError,match='ภาพที่เกี่ยวข้อง'):
            v11.normalize_beats({},[],412.5)
    finally:
        v30._JOB.reset(token)
