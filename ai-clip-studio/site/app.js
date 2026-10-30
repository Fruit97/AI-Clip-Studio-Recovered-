'use strict';
(() => {
  const el = id => document.getElementById(id);
  let active = 'upload', file = null, running = false, timer = null;
  const maxUploadBytes=1024*1048576;
  localStorage.removeItem('ai_clip_studio_active_job_v5');
  localStorage.removeItem('ai_clip_studio_active_job_v7');
  const storageKey='ai_clip_studio_active_job_v11';
  localStorage.removeItem('ai_clip_studio_active_job_v8');
  const selected = {length: '30', aspect: '9:16', voice:'female'};
  const error = msg => {el('formError').textContent = msg;el('formError').hidden = !msg;};
  const show = (id, on) => el(id).classList.toggle('hidden', !on);
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    active = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => {b.classList.toggle('active', b===tab);b.setAttribute('aria-selected', String(b===tab));});
    show('uploadArea', active === 'upload');show('linkArea', active === 'link');error('');
  }));
  for(const [id, key] of [['lengths','length'], ['aspects','aspect'], ['voices','voice']]){
    el(id).querySelectorAll('button').forEach(b => b.addEventListener('click',()=>{
      selected[key]=b.dataset.val;
      el(id).querySelectorAll('button').forEach(x=>x.classList.toggle('selected',x===b));
    }));
  }
  el('showKey').addEventListener('click',()=>{el('apiKey').type=el('apiKey').type==='password'?'text':'password';});
  const zone=el('uploadArea'), input=el('videoFile');
  const setFile=f=>{if(!f)return;file=f;el('uploadTitle').textContent=f.name;el('uploadHint').textContent=(f.size/1048576).toFixed(1)+' MB — พร้อมประมวลผล';zone.classList.add('chosen');error('');};
  zone.addEventListener('click',()=>input.click());
  zone.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();input.click();}});
  input.addEventListener('change',()=>setFile(input.files?.[0]));
  ['dragenter','dragover'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.add('dragover');}));
  ['dragleave','drop'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.remove('dragover');if(ev==='drop')setFile(e.dataTransfer?.files?.[0]);}));
  const getFileUrl=(job,kind)=>`/api/jobs/${encodeURIComponent(job.id)}/files/${kind}?token=${encodeURIComponent(job.token)}`;
  const finish = job => {
    running=false;el('submitBtn').disabled=false;el('submitBtn').querySelector('span:nth-child(2)').textContent='สร้างคลิปใหม่อีกครั้ง';
    rememberJob(currentJob);
    show('progressBox',false);show('resultBox',true);
    el('resultTitle').textContent=job.title || 'คลิปสรุปของคุณ';
    el('resultSummary').textContent=job.summary || '';
    el('sourceModeNote').textContent=job.mode_note || '';
    el('sourceModeNote').classList.toggle('warning-note',job.mode==='graphics');
    el('durationInfo').textContent='ความยาว '+(job.seconds||'-')+' วินาที';
    el('resultScript').textContent=job.script || '';
    el('resultVideo').src=getFileUrl(currentJob,'video')+'&preview=true';
    el('downloadVideo').href=getFileUrl(currentJob,'video');
    el('downloadScript').href=getFileUrl(currentJob,'script');
    el('downloadSubs').href=getFileUrl(currentJob,'captions');
    el('downloadCover').href=getFileUrl(currentJob,'cover');
    el('downloadSubs').style.display=el('captions').checked?'':'none';
  };
  let currentJob=null;
  const rememberJob = job => { currentJob=job; sessionStorage.setItem(storageKey,JSON.stringify(job)); localStorage.setItem(storageKey,JSON.stringify(job)); };
  const forgetJob = () => { sessionStorage.removeItem(storageKey); localStorage.removeItem(storageKey); };
  try {
    const restored=JSON.parse(localStorage.getItem(storageKey)||'null');
    if(restored?.id && restored?.token){
      currentJob=restored;running=true;el('submitBtn').disabled=true;
      show('emptyState',false);show('progressBox',true);
      el('progressStep').textContent='กำลังกู้สถานะงานจากเซิร์ฟเวอร์…';
      poll();timer=setInterval(()=>{if(running&&currentJob)poll();else clearInterval(timer);},3000);
    }
  }catch(e){forgetJob();}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden && currentJob)poll();});
  async function poll(){
    if(!currentJob)return;
    try{
      const r=await fetch(`/api/jobs/${encodeURIComponent(currentJob.id)}?token=${encodeURIComponent(currentJob.token)}`,{cache:'no-store'});
      if(!r.ok){
        const payload=await r.json().catch(()=>({}));
        if(r.status===404 || r.status===410){
          clearInterval(timer);running=false;el('submitBtn').disabled=false;forgetJob();currentJob=null;
          show('progressBox',false);show('emptyState',true);
          error(typeof payload.detail==='string'?payload.detail:'งานเดิมสูญหายจากเซิร์ฟเวอร์ กรุณาอัปโหลดไฟล์อีกครั้ง');
          return;
        }
        throw new Error(typeof payload.detail==='string'?payload.detail:'ไม่สามารถตรวจสอบสถานะงานได้');
      }
      const job=await r.json();
      el('progressStep').textContent=job.step||'กำลังประมวลผล';
      el('progressPercent').textContent=(job.progress||0)+'%';
      el('progressBar').style.width=(job.progress||0)+'%';
      if(job.state==='done'){clearInterval(timer);show('resumeV11',false);finish(job);}
      else if(job.state==='error'||job.state==='interrupted'){
        clearInterval(timer);running=false;el('submitBtn').disabled=false;
        el('submitBtn').querySelector('span:nth-child(2)').textContent='สร้างคลิปใหม่';
        show('progressBox',true);show('emptyState',false);
        show('resumeV11',true);error((job.step||'งานไม่สำเร็จ')+' — '+(job.error||'เกิดข้อผิดพลาด'));
        el('progressStep').textContent='งานถูกขัดจังหวะ — สามารถลองทำต่อจากจุดที่บันทึกไว้ได้';
      }
    } catch(e){el('progressStep').textContent='ตรวจสอบงานไม่ได้ชั่วคราว: '+(e.message||'การเชื่อมต่อล้มเหลว')+' — กำลังเชื่อมต่อใหม่';}
  }

  const getJson = async (url, options) => {
    const res=await fetch(url,options);
    const data=await res.json().catch(()=>({}));
    if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:`เซิร์ฟเวอร์ตอบกลับ HTTP ${res.status}`);
    return data;
  };
  const formOptions = (body) => {
    body.append('length',selected.length);body.append('voice',selected.voice);
    body.append('aspect',selected.aspect);body.append('tone',el('tone').value);
    body.append('captions',String(el('captions').checked));body.append('keep_sound',String(el('keepSound').checked));
    body.append('rights','true');body.append('font_style',el('subtitleFont').value);
  };
  async function sendLargeFile(video, key){
    const init=await getJson('/api/uploads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:video.name,size:video.size})});
    let position=0;
    const qs='token='+encodeURIComponent(init.token);
    while(position<video.size){
      let attempts=0;
      while(true){
        try{
          const bytes=video.slice(position,Math.min(video.size,position+init.chunk_bytes));
          const data=await getJson(`/api/uploads/${init.id}/chunks?${qs}&offset=${position}`,{method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:bytes});
          position=data.received;
          const pct=Math.floor(position/video.size*100);
          el('progressPercent').textContent=pct+'%';el('progressBar').style.width=pct+'%';
          el('progressStep').textContent=`กำลังอัปโหลดไฟล์ ${pct}% (เสร็จแล้วจะประมวลผลต่อบนเซิร์ฟเวอร์)`;
          break;
        }catch(e){
          attempts++;
          if(attempts>4)throw Error('อัปโหลดขัดข้อง กรุณาเลือกไฟล์เดิมแล้วลองใหม่: '+e.message);
          await new Promise(resolve=>setTimeout(resolve,1000*attempts));
          const status=await getJson(`/api/uploads/${init.id}?${qs}`);
          position=status.received;
          if(position>=video.size)break;
        }
      }
    }
    const body=new FormData();body.append('api_key',key);formOptions(body);
    return await getJson(`/api/uploads/${init.id}/complete?${qs}`,{method:'POST',body});
  }

  el('studioForm').addEventListener('submit',async e=>{
    e.preventDefault();if(running)return;
    const key=el('apiKey').value.trim(), url='';
    error('');
    if(active==='upload'&&!file)return error('กรุณาเลือกไฟล์วิดีโอ');
    if(active==='upload'&&file.size>maxUploadBytes)return error('ไฟล์ใหญ่เกิน 1 GB');
    if(active==='link'&&!url)return error('กรุณาวางลิงก์วิดีโอ');
    if(!key)return error('กรุณาใส่ Gemini API Key');
    if(!el('rights').checked)return error('กรุณายืนยันสิทธิ์ใช้งานวิดีโอ');
    running=true;el('submitBtn').disabled=true;el('submitBtn').querySelector('span:nth-child(2)').textContent='กำลังส่งข้อมูล…';
    try{
      let data;
      if(active==='upload'){
        show('emptyState',false);show('resultBox',false);show('progressBox',true);
        data=await sendLargeFile(file,key);
      }else{
        const body=new FormData();body.append('url',url);body.append('api_key',key);formOptions(body);
        data=await getJson('/api/jobs',{method:'POST',body});
      }
      rememberJob(data);show('resumeV11',false);
      // Keep key only in this page's memory; the encrypted vault is optional.
      show('emptyState',false);show('resultBox',false);show('progressBox',true);
      el('progressStep').textContent='กำลังเตรียมงาน';el('progressPercent').textContent='0%';
      el('submitBtn').querySelector('span:nth-child(2)').textContent='กำลังสร้างคลิป…';
      clearInterval(timer);await poll();if(running && currentJob)timer=setInterval(poll,3000);
    }catch(err){show('progressBox',false);show('emptyState',true);running=false;el('submitBtn').disabled=false;el('submitBtn').querySelector('span:nth-child(2)').textContent='เริ่มสร้างคลิปด้วย AI';error(err.message||'เชื่อมต่อไม่สำเร็จ');}
  });
  el('resumeV11').addEventListener('click', async()=>{
    if(!currentJob)return error('ไม่พบงานเก่า');
    const key=el('apiKey').value.trim();
    if(!key)return error('ปลดล็อก Gemini API Key ก่อนทำงานต่อ');
    const body=new FormData();body.append('api_key',key);
    el('resumeV11').disabled=true;
    try{
      await getJson(`/api/jobs/${encodeURIComponent(currentJob.id)}/resume?token=${encodeURIComponent(currentJob.token)}`,
                    {method:'POST',body});
      show('resumeV11',false);running=true;el('submitBtn').disabled=true;error('');
      await poll();clearInterval(timer);
      if(running&&currentJob)timer=setInterval(poll,3000);
    }catch(ex){error(ex.message);el('resumeV11').disabled=false;}
  });
  // AES-GCM browser-only key vault. Never persist plaintext keys or passphrases.
  const vaultStorage='ai_clip_studio_encrypted_keys_v8';
  let vaultKeys=[], vaultPassword=null;
  const encoder=new TextEncoder(),decoder=new TextDecoder();
  const toB64=bytes=>btoa(Array.from(bytes,x=>String.fromCharCode(x)).join(''));
  const fromB64=text=>Uint8Array.from(atob(text),c=>c.charCodeAt(0));
  const vaultMessage=(message, failed=false)=>{el('vaultStatus').textContent=message;el('vaultStatus').style.color=failed?'#ffc0c2':'#9fe8d6';};
  const vaultAvailable=()=>window.crypto&&window.crypto.subtle&&location.protocol==='https:';
  const vaultCipher=async (password,salt)=>crypto.subtle.deriveKey(
    {name:'PBKDF2',salt,iterations:210000,hash:'SHA-256'},
    await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveKey']),
    {name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  async function openVault(password){
    const record=JSON.parse(localStorage.getItem(vaultStorage)||'null');
    if(!record){vaultKeys=[];vaultPassword=password;renderVaultKeys();vaultMessage('สร้างคลังคีย์ใหม่แล้ว กด “บันทึกคีย์ปัจจุบัน” ได้เลย');return;}
    try{
      const key=await vaultCipher(password,fromB64(record.salt));
      const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:fromB64(record.iv)},key,fromB64(record.cipher));
      const parsed=JSON.parse(decoder.decode(clear));
      if(!Array.isArray(parsed))throw Error('invalid vault');
      vaultKeys=parsed.filter(x=>typeof x.label==='string'&&typeof x.key==='string');
      vaultPassword=password;renderVaultKeys();vaultMessage(`ปลดล็อกแล้ว พบคีย์ที่บันทึก ${vaultKeys.length} รายการ`);
    }catch(e){throw Error('รหัสผ่านไม่ถูกต้อง หรือข้อมูลคลังคีย์เสียหาย');}
  }
  async function persistVault(){
    if(!vaultPassword)throw Error('กรุณาปลดล็อกคลังคีย์ก่อน');
    const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
    const aes=await vaultCipher(vaultPassword,salt);
    const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv},aes,encoder.encode(JSON.stringify(vaultKeys)));
    localStorage.setItem(vaultStorage,JSON.stringify({version:1,salt:toB64(salt),iv:toB64(iv),cipher:toB64(new Uint8Array(encrypted))}));
  }
  function renderVaultKeys(){
    const select=el('savedKeySelect');select.replaceChildren();
    if(!vaultPassword){select.add(new Option('คลังคีย์ล็อกอยู่',''));return;}
    if(vaultKeys.length===0){select.add(new Option('ยังไม่มีคีย์ที่บันทึก',''));return;}
    for(let i=0;i<vaultKeys.length;i++)select.add(new Option(vaultKeys[i].label,String(i)));
  }
  el('unlockVault').addEventListener('click',async()=>{
    if(!vaultAvailable())return vaultMessage('ต้องเปิดผ่าน HTTPS เพื่อเข้ารหัส API Key',true);
    const pass=el('vaultPassphrase').value;
    if(pass.length<8)return vaultMessage('รหัสผ่านคลังคีย์ต้องยาวอย่างน้อย 8 ตัวอักษร',true);
    try{await openVault(pass);el('vaultPassphrase').value='';}catch(e){vaultMessage(e.message,true);}
  });
  el('saveVaultKey').addEventListener('click',async()=>{
    if(!vaultAvailable())return vaultMessage('เบราว์เซอร์นี้ไม่รองรับการเข้ารหัส',true);
    if(!vaultPassword){
      const pass=el('vaultPassphrase').value;
      if(pass.length<8)return vaultMessage('ใส่รหัสผ่านอย่างน้อย 8 ตัวอักษร แล้วกดปลดล็อกก่อน',true);
      try{await openVault(pass);el('vaultPassphrase').value='';}catch(e){return vaultMessage(e.message,true);}
    }
    const value=el('apiKey').value.trim(),label=el('vaultLabel').value.trim()||`Gemini Key ${vaultKeys.length+1}`;
    if(value.length<12)return vaultMessage('ใส่ Gemini API Key ที่ช่องด้านบนก่อนกดบันทึก',true);
    const index=vaultKeys.findIndex(x=>x.label===label);
    if(index>=0)vaultKeys[index]={label,key:value};else vaultKeys.push({label,key:value});
    try{await persistVault();renderVaultKeys();el('savedKeySelect').value=String(index>=0?index:vaultKeys.length-1);vaultMessage(`บันทึกคีย์ “${label}” แบบเข้ารหัสแล้ว`);}catch(e){vaultMessage('บันทึกไม่ได้: '+e.message,true);}
  });
  el('useVaultKey').addEventListener('click',()=>{
    const idx=Number(el('savedKeySelect').value);
    if(!vaultPassword||!el('savedKeySelect').value||!vaultKeys[idx])return vaultMessage('ปลดล็อกแล้วเลือกคีย์ก่อน',true);
    el('apiKey').value=vaultKeys[idx].key;vaultMessage(`พร้อมใช้งาน “${vaultKeys[idx].label}”`);
  });
  el('deleteVaultKey').addEventListener('click',async()=>{
    const idx=Number(el('savedKeySelect').value);
    if(!vaultPassword||!el('savedKeySelect').value||!vaultKeys[idx])return vaultMessage('เลือกคีย์ที่ต้องการลบก่อน',true);
    const name=vaultKeys[idx].label;
    if(!confirm(`ลบคีย์ที่บันทึกชื่อ “${name}” หรือไม่?`))return;
    vaultKeys.splice(idx,1);try{await persistVault();renderVaultKeys();vaultMessage('ลบคีย์ที่เลือกแล้ว');}catch(e){vaultMessage(e.message,true);}
  });
  el('lockVault').addEventListener('click',()=>{vaultKeys=[];vaultPassword=null;el('apiKey').value='';renderVaultKeys();vaultMessage('ล็อกคลังคีย์แล้ว คีย์ที่บันทึกยังอยู่ในอุปกรณ์นี้');});
  el('wipeVault').addEventListener('click',()=>{
    if(!confirm('ลบคีย์ที่บันทึกทั้งหมดใน Chrome เครื่องนี้อย่างถาวร?'))return;
    localStorage.removeItem(vaultStorage);vaultKeys=[];vaultPassword=null;el('apiKey').value='';renderVaultKeys();vaultMessage('ลบคลังคีย์ทั้งหมดแล้ว');
  });
  renderVaultKeys();
  if(localStorage.getItem(vaultStorage))vaultMessage('พบคลังคีย์ที่บันทึกไว้ ใส่รหัสผ่านแล้วกดปลดล็อก');
})();
