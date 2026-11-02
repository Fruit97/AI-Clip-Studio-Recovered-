'use strict';
const el = id => document.getElementById(id);
const VOICES_KEY='thaivoicelab.v11.voices';
const KEY_STORE='thaivoicelab.v11.key';
const KEY_REMEMBER='thaivoicelab.v11.remember';
const VOICE_ID=/^[A-Za-z0-9_-]{8,80}$/;
let voices=[];
let busy=false;
let previewUrl=null, outputUrl=null, toastTimeout=null;
function showToast(message,isError){
  const t=el('toast'); t.textContent=message; t.classList.toggle('error',!!isError); t.hidden=false;
  clearTimeout(toastTimeout); toastTimeout=setTimeout(()=>{t.hidden=true},6000);
}
function setBusy(on,what){
  busy=on;el('busy').hidden=!on;el('busyText').textContent=what||'กำลังประมวลผล...';
  el('cloneBtn').disabled=on;el('speakBtn').disabled=on;
}
function key(){
  const v=el('key').value.trim();
  if(!v)throw Error('กรุณาใส่ ElevenLabs API Key ก่อน');
  return v;
}
function saveKey(){
  const k=el('key').value.trim();
  if(el('rememberKey').checked){
    localStorage.setItem(KEY_STORE,k);localStorage.setItem(KEY_REMEMBER,'1');sessionStorage.removeItem(KEY_STORE);
  }else{
    localStorage.removeItem(KEY_STORE);localStorage.removeItem(KEY_REMEMBER);
    sessionStorage.setItem(KEY_STORE,k);
  }
}
async function validateResponse(r){
  if(r.ok)return r;
  let message='เซิร์ฟเวอร์ตอบกลับผิดพลาด (HTTP '+r.status+')';
  try{const data=await r.json();if(typeof data.detail==='string')message=data.detail}catch{}
  throw Error(message);
}
function persistVoices(){localStorage.setItem(VOICES_KEY,JSON.stringify(voices))}
function drawVoices(selectedId){
  const list=el('voices'), select=el('voiceSelect');
  const previous=selectedId||select.value;
  list.replaceChildren();select.replaceChildren();
  const option=document.createElement('option');option.value='';option.textContent='— เลือกเสียงของคุณ —';select.append(option);
  el('voiceCount').textContent=voices.length+' เสียง';
  if(!voices.length){
    const p=document.createElement('p');p.className='hint';p.textContent='ยังไม่มีเสียงต้นแบบ เริ่มโคลนเสียงหรือเพิ่ม Voice ID เดิม';list.append(p);
  }
  voices.forEach(voice=>{
    const op=document.createElement('option');op.value=voice.id;op.textContent=voice.name;select.append(op);
    const entry=document.createElement('div');entry.className='voice';
    const info=document.createElement('div');const title=document.createElement('strong');title.textContent=voice.name;
    const id=document.createElement('small');id.textContent='ID: '+voice.id.slice(0,7)+'...';info.append(title,id);
    const actions=document.createElement('div');actions.className='actions';
    const choose=document.createElement('button');choose.className='outline';choose.type='button';choose.textContent='เลือก';
    choose.addEventListener('click',()=>{select.value=voice.id;showToast('เลือกเสียง '+voice.name+' แล้ว')});
    const remove=document.createElement('button');remove.className='remove';remove.type='button';remove.textContent='ลบ';
    remove.addEventListener('click',()=>removeVoice(voice));
    actions.append(choose,remove);entry.append(info,actions);list.append(entry);
  });
  if(voices.some(v=>v.id===previous))select.value=previous;
}
function addVoice(voice){
  voices=[voice,...voices.filter(v=>v.id!==voice.id)].slice(0,70);
  persistVoices();drawVoices(voice.id);
}
async function removeVoice(voice){
  if(busy)return;
  if(!confirm('ยืนยันลบเสียง "'+voice.name+'" ออกจากบัญชี ElevenLabs อย่างถาวร?'))return;
  try{
    setBusy(true,'กำลังลบเสียง...');
    const r=await fetch('/api/voices/'+encodeURIComponent(voice.id),{method:'DELETE',headers:{'X-ElevenLabs-Key':key()}});
    await validateResponse(r);
    voices=voices.filter(v=>v.id!==voice.id);persistVoices();drawVoices();
    showToast('ลบเสียงเรียบร้อยแล้ว');
  }catch(e){showToast(e.message,true)}finally{setBusy(false)}
}
function chooseFile(){
  const f=el('voiceFile').files[0];
  if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null}
  el('samplePreview').hidden=true;
  if(!f){el('sampleTitle').textContent='แตะเพื่อเลือกไฟล์เสียง';return}
  if(f.size>20*1024*1024){showToast('ไฟล์เสียงใหญ่เกิน 20 MB',true);el('voiceFile').value='';return}
  el('sampleTitle').textContent=f.name;
  previewUrl=URL.createObjectURL(f);el('samplePreview').src=previewUrl;el('samplePreview').hidden=false;
}
async function clone(e){
  e.preventDefault();if(busy)return;
  const f=el('voiceFile').files[0],name=el('voiceName').value.trim();
  if(!f||!name||!el('consent').checked){showToast('กรุณากรอกข้อมูลและยืนยันสิทธิ์ก่อน',true);return}
  if(f.size>20*1024*1024){showToast('ไฟล์เสียงใหญ่เกิน 20 MB',true);return}
  try{
    saveKey();const k=key();setBusy(true,'กำลังส่งไฟล์และโคลนเสียง...');
    const form=new FormData();form.append('file',f);form.append('name',name);form.append('consent','true');
    const r=await fetch('/api/clone',{method:'POST',headers:{'X-ElevenLabs-Key':k},body:form});
    await validateResponse(r);const data=await r.json();
    addVoice({id:data.voice_id,name:data.name});
    el('cloneForm').reset();chooseFile();
    showToast(data.requires_verification?'สร้างเสียงแล้ว แต่ผู้ให้บริการกำหนดให้ยืนยันเสียงก่อน':'โคลนเสียงสำเร็จ! เลือกเสียงนี้เพื่อสร้าง MP3');
  }catch(e){showToast(e.message,true)}finally{setBusy(false)}
}
async function speak(e){
  e.preventDefault();if(busy)return;
  const voice_id=el('voiceSelect').value,text=el('scriptText').value.trim();
  if(!voice_id||!text){showToast('กรุณาเลือกเสียงและพิมพ์ข้อความ',true);return}
  try{
    saveKey();const k=key();setBusy(true,'AI กำลังสร้างเสียงภาษาไทย...');
    const r=await fetch('/api/speak',{method:'POST',headers:{'X-ElevenLabs-Key':k,'Content-Type':'application/json'},body:JSON.stringify({voice_id,text})});
    await validateResponse(r);const data=await r.blob();
    if(outputUrl)URL.revokeObjectURL(outputUrl);
    outputUrl=URL.createObjectURL(data);el('player').src=outputUrl;el('download').href=outputUrl;
    el('output').hidden=false;el('placeholder').hidden=true;el('output').scrollIntoView({behavior:'smooth',block:'nearest'});
    showToast('สร้างเสียงสำเร็จ พร้อมฟังและดาวน์โหลด MP3');
  }catch(e){showToast(e.message,true)}finally{setBusy(false)}
}
function init(){
  try{
    const raw=JSON.parse(localStorage.getItem(VOICES_KEY)||'[]');
    voices=Array.isArray(raw)?raw.filter(v=>v&&VOICE_ID.test(v.id)&&typeof v.name==='string').slice(0,70):[];
  }catch{voices=[]}
  const remember=localStorage.getItem(KEY_REMEMBER)==='1';el('rememberKey').checked=remember;
  el('key').value=(remember?localStorage.getItem(KEY_STORE):sessionStorage.getItem(KEY_STORE))||'';
  el('rememberKey').addEventListener('change',saveKey);
  el('key').addEventListener('change',saveKey);
  el('showKey').addEventListener('click',()=>{const input=el('key');input.type=input.type==='password'?'text':'password';el('showKey').textContent=input.type==='text'?'ซ่อน':'แสดง'});
  el('voiceFile').addEventListener('change',chooseFile);
  el('scriptText').addEventListener('input',()=>{el('counter').textContent=el('scriptText').value.length+' / 2,000'});
  el('cloneForm').addEventListener('submit',clone);el('speakForm').addEventListener('submit',speak);
  el('importBtn').addEventListener('click',()=>el('importDialog').showModal());
  el('cancelImport').addEventListener('click',()=>el('importDialog').close());
  el('importForm').addEventListener('submit',e=>{
    e.preventDefault();const id=el('importId').value.trim(),name=el('importName').value.trim();
    if(!VOICE_ID.test(id)||!name||name.length>75){showToast('กรุณากรอกชื่อและ Voice ID ให้ถูกต้อง',true);return}
    addVoice({id,name});el('importDialog').close();el('importForm').reset();showToast('เพิ่ม Voice ID เรียบร้อยแล้ว');
  });
  drawVoices();
}
document.addEventListener('DOMContentLoaded',init);