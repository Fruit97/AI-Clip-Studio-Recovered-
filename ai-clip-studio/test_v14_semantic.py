import json
from types import SimpleNamespace
import pytest
import v14_semantic as v14

SHOTS=[
  {'id':'s000','start':0,'end':3},
  {'id':'s001','start':3,'end':6},
  {'id':'s002','start':6,'end':9},
]
SCENES=[
 {'id':'s000','description':'สุนัขกระโจนขึ้นจากบ่อน้ำ','tags':['สัตว์','กระโจน']},
 {'id':'s001','description':'รถไฟแล่นผ่านสถานีที่มีคนรอ','tags':['รถไฟ','สถานี']},
 {'id':'s002','description':'หญิงสาวกำลังผัดอาหารในกระทะ','tags':['อาหาร','ทำครัว']},
]

def data(beats):
 return {'_v14_evidence_required':True,'_v14_candidate_shots':['s000','s001','s002'],
         'scenes':SCENES, 'beats':beats}

def match(sid,score=.94,evidence='เห็นวัตถุหรือการกระทำนี้ในช็อตจริง'):
 return {'id':sid,'score':score,'evidence':evidence}

def test_narration_can_be_any_subject_without_special_casing():
 beats=[
  {'narration':'เจ้าสุนัขกระโดดลงน้ำ','caption':'สุนัขกระโดด','shot_id':'s000',
   'visual_matches':[match('s000',.95,'เห็นสุนัขกำลังกระโจนลงน้ำ')]},
  {'narration':'รถไฟกำลังเข้าสถานี','caption':'รถไฟเข้าชานชาลา','shot_id':'s001',
   'visual_matches':[match('s001',.92,'เห็นขบวนรถไฟแล่นผ่านชานชาลา')]},
  {'narration':'ผู้หญิงกำลังทำอาหาร','caption':'ทำอาหารในครัว','shot_id':'s002',
   'visual_matches':[match('s002',.88,'เห็นผู้หญิงกำลังผัดกระทะ')]},
 ]
 a=v14.normalize(data(beats), SHOTS,9,lambda *_: (_ for _ in ()).throw(Exception('legacy should not run')))
 assert [b['shot_id'] for b in a['beats']]==['s000','s001','s002']
 assert len(a['visual_matching_report']['excluded_beats'])==0
 assert a['script']==' '.join(b['narration'] for b in beats)

def test_unrelated_shots_removed_before_speech_creation():
 beats=[{'narration':'รถกำลังพุ่งชนต้นไม้', 'shot_id':'s001',
         'visual_matches':[match('s001',.32,'เห็นเพียงขบวนรถไฟแล่นผ่าน')]},
        {'narration':'หญิงสาวกำลังผัดอาหาร', 'shot_id':'s002',
         'visual_matches':[match('s002',.96,'หญิงสาวกำลังผัดอาหารในกระทะ')]}]
 result=v14.normalize(data(beats), SHOTS,9,lambda *_:None)
 assert len(result['beats'])==1
 assert result['beats'][0]['shot_id']=='s002'
 assert result['visual_matching_report']['excluded']==1
 assert 'พุ่งชน' not in result['script']

def test_no_keyword_fallback_when_evidence_missing():
 a=data([{'narration':'หญิงสาวทำอาหาร','visual_keywords':['อาหาร'],'shot_id':'s002',
          'visual_matches':[]}])
 with pytest.raises(RuntimeError,match='ไม่มีฉาก'):
  v14.normalize(a,SHOTS,9,lambda *_:None)

def test_topic_agnostic_replaces_exact_keyword_match():
 # 'สุนัข' and 'หมา' do not have to be lexically identical.
 beat={'narration':'เจ้าหมาโดดลงสระ','shot_id':'s000','visual_keywords':['หมา','สระ'],
       'visual_matches':[match('s000',.91,'เห็นสุนัขกระโดดลงบ่อน้ำ')]}
 a=v14.normalize(data([beat]),SHOTS,9,lambda *_:None)
 assert a['beats'][0]['shot_id']=='s000'
 assert a['beats'][0]['related_shots']==['s000']

def test_invalid_id_is_never_used_even_high_score():
 a=data([{'narration':'หญิงสาวทำอาหาร','shot_id':'nonexistent',
          'visual_matches':[match('nonexistent',.99)]}])
 with pytest.raises(RuntimeError,match='ไม่มีฉาก'):
  v14.normalize(a,SHOTS,9,lambda *_:None)

def test_legacy_checkpoint_compatibility():
 legacy={'beats':[{'narration':'something'}]}
 assert v14.normalize(legacy,SHOTS,9,lambda *_: {'ok':True})=={'ok':True}

def test_prompt_does_not_use_hardcoded_sea_rule():
 prompt=v14.make_prompt([{'id':'s000','start':0,'end':1}],15,'สารคดี')
 assert 'UNIVERSAL' in prompt
 assert 'visual_matches' in prompt
 assert 'if narration says sea' not in prompt

def test_ai_upload_only_called_once_and_marks_strict():
 class FakeClient:
  def delete(self,*args,**kwargs):pass
 def fake_api(client,method,url,key,**kwargs):
  assert 'generateContent' in url
  assert 'UNIVERSAL' in kwargs['json']['contents'][0]['parts'][0]['text']
  return {'candidates':[{'content':{'parts':[{'text':json.dumps({'scenes':SCENES,'beats':[
   {'narration':'หญิงสาวทำอาหาร','shot_id':'s002','visual_matches':[match('s002',.97)]}]},ensure_ascii=False)}]}}]}
 ns={'upload_gemini':lambda *_:{'uri':'files/fake','name':'files/fake'},
     'get_json':fake_api,'BASE':'https://gemini.invalid','MODEL':'fake'}
 a=v14.analyze_proxy(ns,FakeClient(),'proxy.mp4','fakekey',9,SHOTS,15,'สารคดี')
 assert a['_v14_evidence_required']
 assert a['_v14_candidate_shots']==['s000','s001','s002']
