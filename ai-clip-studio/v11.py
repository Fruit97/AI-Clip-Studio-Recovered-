"""AI Clip Studio V11: upload-first, source-grounded, low-RAM production pipeline.
All media segments are rendered from user-uploaded source, never invented imagery.
Checkpoint files are local; external durability needs separately configured object storage.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata

VERSION = "v16-frame-aware-render-validation-2026-10-31"
WIDTH, HEIGHT, FPS = 720, 1280, 30
IMAGE_HEIGHT = 952
SEGMENT_MAX_SECONDS = 4.5
SCENE_MIN_SECONDS = 1.0


def atom_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text('utf-8'))
    except (FileNotFoundError, ValueError):
        return default


def ffmpeg_run(cmd, *, timeout=240):
    clean = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-threads', '1', '-filter_threads', '1', '-filter_complex_threads', '1'] + list(cmd)
    try:
        p = subprocess.run(clean, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('FFmpeg เกินเวลาประมวลผลระหว่างเรนเดอร์ช็อต') from exc
    if p.returncode:
        detail = p.stderr.decode('utf-8','replace')[-1200:] or f'exit {p.returncode}'
        raise RuntimeError('FFmpeg: '+detail)


def media_ok(path, min_seconds=.2, *, expect_video=True):
    path=Path(path)
    if not path.exists() or path.stat().st_size < 1000: return False
    try:
        p = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type',
                            '-of','json',str(path)],capture_output=True,text=True,timeout=20)
        d=json.loads(p.stdout)
        if p.returncode or float(d.get('format',{}).get('duration',0)) < min_seconds: return False
        if expect_video and not any(s.get('codec_type')=='video' for s in d.get('streams',[])):return False
        return True
    except (ValueError, OSError, subprocess.TimeoutExpired):return False


def duration_of(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],capture_output=True,text=True,timeout=25)
    if p.returncode:raise RuntimeError('ไม่สามารถอ่านความยาววิดีโอต้นฉบับ')
    return float(p.stdout.strip())


def make_proxy(source, dest):
    if media_ok(dest,1):return dest
    tmp=Path(str(dest)+'.temp.mp4')
    # Higher resolution sources are decoded once, but stored proxy is at most 640px wide,
    # and no more than 8 fps. No full-size image buffers are retained in Python.
    ffmpeg_run(['-i',str(source),'-map','0:v:0','-map','0:a:0?',
                '-vf','fps=8,scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p',
                '-c:v','libx264','-preset','ultrafast','-crf','31','-threads','1',
                '-c:a','aac','-ac','1','-b:a','40k','-movflags','+faststart',str(tmp)],timeout=600)
    if not media_ok(tmp,1):raise RuntimeError('ไม่สามารถสร้าง analysis proxy จากต้นฉบับ')
    tmp.replace(dest)
    return dest


def detect_shots(proxy, duration):
    """Find real source cut boundaries from scene differences; supplement sparse cuts.
    Timestamps are in original seconds because fps changes preserve presentation time.
    """
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(proxy),'-vf',
                      "select='gt(scene,0.32)',showinfo",'-an','-f','null','-'],
                     stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=360)
    raw=p.stderr.decode('utf-8','replace')
    cuts=[0.0]
    for match in re.finditer(r'pts_time:([\d.]+)',raw):
        t=float(match.group(1))
        if SCENE_MIN_SECONDS < t < duration-.5 and t-cuts[-1]>=SCENE_MIN_SECONDS:
            cuts.append(t)
    cuts.append(duration)
    # Split long uninterrupted sources to keep individual shots useful for matching.
    result=[]
    for a,b in zip(cuts,cuts[1:]):
        count=max(1,math.ceil((b-a)/6.0))
        for j in range(count):
            st=a+j*(b-a)/count
            ed=a+(j+1)*(b-a)/count
            if ed-st>.3:
                result.append({'id':f's{len(result):03}', 'start':round(st,3),'end':round(ed,3)})
    return result[:300]


def _clip(t,lower,upper):return max(lower,min(upper,t))


def analyze_proxy(ns, client, proxy, key, source_duration, shots, length, tone):
    remote=ns['upload_gemini'](client,proxy,key)
    try:
        timecodes=[{'id':s['id'],'start':s['start'],'end':s['end']} for s in shots[:160]]
        prompt=(
          'You are a Thai short-video documentary editor. Actually observe the given VIDEO, '
          'do NOT invent claims or any visual frames. Respond with JSON only. '
          'These timestamp ranges were detected from the original footage: '+json.dumps(timecodes)+'. '
          'Output fields: title (Thai), summary (Thai), script (natural Thai voiceover), '
          'scenes (array of {id, description in Thai, tags array of 2-5 Thai visual nouns}, '
          'for each observed shot; include only visible subjects), '
          'beats (array of {narration, caption, shot_id, visual_keywords}). '
          'Every beat must be based on an observed scene. Assign shot_id to the ACTUAL matching image '
          'at the time that sentence is spoken. The scene must show the sentence subject: if narration '
          'says sea, show actual sea, not a studio presenter; use only shots in provided ranges. '
          'Structure: compelling accurate hook, exposition, climax, ending. Keep narration within '
          f'about {length} seconds spoken Thai, style {tone}. Avoid long narration if footage is limited. '
          'All narration beats ordered to support a logical story, no scene fabrication, '
          'no external footage, no repetitive shots. Captions short for 2-line bold subtitles.'
        )
        body={'contents':[{'parts':[{'text':prompt},
                {'fileData':{'mimeType':'video/mp4','fileUri':remote['uri']}}]}],
              'generationConfig':{'responseMimeType':'application/json','temperature':0.18}}
        result=ns['get_json'](client,'POST',f"{ns['BASE']}/models/{ns['MODEL']}:generateContent",key,json=body)
        parts=result.get('candidates',[{}])[0].get('content',{}).get('parts',[])
        raw='\n'.join(p.get('text','') for p in parts)
        raw=re.sub(r'^```(?:json)?\s*|\s*```$', '',raw.strip())
        analysis=json.loads(raw)
        if not isinstance(analysis.get('beats'),list) or not analysis['beats']:
            raise RuntimeError('Gemini ไม่ส่งรายการฉากที่จับคู่กับบทพากย์ กรุณาลองวิดีโอใหม่')
        return analysis
    finally:
        try:client.delete(f"{ns['BASE']}/{remote['name']}",headers={'x-goog-api-key':key},timeout=15)
        except Exception:pass


def _thai_match(line,desc,tags):
    """Conservative transparent lexical fallback, not a replacement for multimodal AI."""
    keys=[str(v).strip().lower() for v in (line or []) if str(v).strip()]
    hay=' '.join([str(desc),*tags]).lower()
    return sum(min(len(k),12) for k in keys if k in hay)


def normalize_beats(analysis, shots, source_duration):
    lookup={s['id']:s for s in shots}
    descriptions={}
    for row in analysis.get('scenes',[]):
        if isinstance(row,dict) and row.get('id') in lookup:
            descriptions[row['id']]={'description':str(row.get('description',''))[:200],
                 'tags':[str(t)[:32] for t in row.get('tags',[])[:6]]}
    beats=[];used=set()
    for entry in analysis.get('beats',[])[:36]:
        if not isinstance(entry,dict):continue
        narration=str(entry.get('narration','')).strip()[:350]
        if len(narration)<3:continue
        keywords=[str(k).strip() for k in entry.get('visual_keywords',[])[:6]]
        preferred=entry.get('shot_id')
        chosen=None
        if preferred in lookup:
            chosen=lookup[preferred]
        else:
            ranked=sorted(shots,key=lambda s:(_thai_match(keywords,descriptions.get(s['id'],{}).get('description',''),descriptions.get(s['id'],{}).get('tags',[])),s['id'] not in used),reverse=True)
            if ranked and _thai_match(keywords,descriptions.get(ranked[0]['id'],{}).get('description',''),descriptions.get(ranked[0]['id'],{}).get('tags',[]))>0:
                chosen=ranked[0]
        # Prefer a different, still relevant source shot when Gemini repeats a segment.
        # Repeating the same image for separate narration beats looks artificial.
        if chosen is not None and chosen['id'] in used:
            alternatives=sorted((shot for shot in shots if shot['id'] not in used),
                key=lambda shot:_thai_match(keywords,
                       descriptions.get(shot['id'],{}).get('description',''),
                       descriptions.get(shot['id'],{}).get('tags',[])),reverse=True)
            if alternatives and _thai_match(keywords,
                        descriptions.get(alternatives[0]['id'],{}).get('description',''),
                        descriptions.get(alternatives[0]['id'],{}).get('tags',[]))>0:
                chosen=alternatives[0]
        if chosen is None: continue
        # If Gemini explicitly names a shot, only trust it when we can verify scene semantics
        # from the returned descriptions. Otherwise use a grounded selected shot; report issues.
        desc=descriptions.get(chosen['id'])
        if desc and keywords and _thai_match(keywords,desc['description'],desc['tags'])==0:
            other=sorted(shots,key=lambda s:_thai_match(keywords,descriptions.get(s['id'],{}).get('description',''),descriptions.get(s['id'],{}).get('tags',[])),reverse=True)
            if other and _thai_match(keywords,descriptions.get(other[0]['id'],{}).get('description',''),descriptions.get(other[0]['id'],{}).get('tags',[]))>0:
                chosen=other[0]
            else:
                continue # Never invent an unrelated shot.
        caption=str(entry.get('caption') or narration).strip()[:65]
        beats.append({'narration':narration,'caption':caption,'shot_id':chosen['id'],
                      'source_start':chosen['start'],'source_end':chosen['end'],
                      'visual_keywords':keywords})
        used.add(chosen['id'])
    if len(beats)<1:raise RuntimeError('ไม่พบภาพที่ตรงกับบทพากย์ในวิดีโอต้นฉบับ กรุณาเปลี่ยนคลิปหรือความยาว')
    analysis['beats']=beats
    analysis['script']=' '.join(b['narration'] for b in beats)
    analysis['captions']=[b['caption'] for b in beats]
    analysis['highlights']=[{'start':b['source_start'],'end':b['source_end']} for b in beats]
    return analysis


def time_beats(beats, voice_duration, source_duration, shots):
    """Approximate phrase timing proportional to Unicode grapheme-like character weights.
    Preserves source shot continuity without looping: preflight rejects insufficient unique footage.
    """
    weights=[max(6,len(re.sub(r'\s+','',b['narration']))) for b in beats]
    total=sum(weights)
    target=[voice_duration*w/total for w in weights]
    cuts=[];source_used=[];timeline_at=0.0
    for i,(beat,need) in enumerate(zip(beats,target)):
        # A beat can use multiple compatible shots but not duplicate a used source interval.
        main=(beat['source_start'],beat['source_end'])
        # Never fill narration time with unrelated frames.
        options=[main]
        remaining=need
        for start,end in options:
            if remaining < 0.025:break
            start=float(start);end=float(end)
            # subtract overlap used by previous segments
            candidates=[(start,end)]
            for ua,ub in source_used:
                out=[]
                for a,b in candidates:
                    if ub<=a or ua>=b:out.append((a,b))
                    else:
                        if a<ua:out.append((a,ua))
                        if ub<b:out.append((ub,b))
                candidates=out
            for a,b in candidates:
                if remaining<0.025:break
                take=min(b-a,remaining)
                if take<0.12:continue
                while take>0:
                    part=min(SEGMENT_MAX_SECONDS,take)
                    cuts.append({'source_start':round(a,3),'duration':round(part,3),'voice_start':round(timeline_at,3),
                                 'caption':beat['caption'],'text':beat['narration'],'shot_id':beat['shot_id']})
                    source_used.append((a,a+part))
                    a+=part;take-=part;remaining-=part;timeline_at+=part
        if remaining>0.3:
            raise RuntimeError('ต้นฉบับมีภาพที่ไม่ซ้ำไม่เพียงพอต่อเสียงพากย์ กรุณาลดความยาวคลิปหรือเพิ่มวิดีโอต้นฉบับ')
    if not cuts:raise RuntimeError('ไม่พบฉากสำหรับตัดต่อ')
    return cuts


def ass_escape(s):
    return str(s).replace('\\','').replace('{','').replace('}','').replace('\n',' ').replace('\r',' ').strip()


def write_ass(caption, duration, path):
    # ASS BGR: yellow = &H0000D8FF; white = &H00FFFFFF
    s=ass_escape(caption)[:74]
    s=''.join(c for c in s if unicodedata.category(c)[0]!='C')
    chars=list(s)
    if len(chars)>30:
        k=min(range(14,len(chars)-7),key=lambda i: abs(i-len(chars)*.50)+(0 if chars[i-1].isspace() else 4))
        a=''.join(chars[:k]).strip();b=''.join(chars[k:]).strip()
        caption_text=r'{\c&HFFFFFF&}'+a+r'\N{\c&H00D8FF&}'+b
    else:
        caption_text=r'{\c&HFFFFFF&}'+s
    sub=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\nWrapStyle: 2\nScaledBorderAndShadow: yes\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Main,Noto Sans Thai,46,&H00FFFFFF,&H0000D8FF,&H0010191A,&H90000000,-1,0,0,0,100,100,0,0,1,2,1,2,40,40,110,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:{duration:05.2f},Main,,0,0,0,,{caption_text}\n'''
    Path(path).write_text(sub,encoding='utf-8')


def render_one(source,voice,dest,ass,segment,has_audio,keep_sound):
    start=segment['source_start'];duration=segment['duration'];voice_start=segment['voice_start']
    source_video=(f'[0:v]split=2[bg][fg];'
                  f'[bg]scale=120:160:force_original_aspect_ratio=increase,crop=120:160,'
                  f'boxblur=5:1,scale=720:{IMAGE_HEIGHT}[blur];'
                  f'[fg]scale=720:{IMAGE_HEIGHT}:force_original_aspect_ratio=decrease[front];'
                  f'[blur][front]overlay=(W-w)/2:(H-h)/2:shortest=1,'
                  f'pad=720:1280:0:0:color=0x12202A,'
                  f'drawbox=x=0:y={IMAGE_HEIGHT}:w=720:h={1280-IMAGE_HEIGHT}:color=0x12202A:t=fill,'
                  f'ass={ass}:fontsdir=/usr/share/fonts/truetype/noto,'
                  f'fps=30,setsar=1,format=yuv420p[vout]')
    # Silence/missing original audio handled by using narration alone.
    inp=['-ss',f'{start:.3f}','-t',f'{duration:.3f}','-i',str(source),
         '-ss',f'{voice_start:.3f}','-t',f'{duration:.3f}','-i',str(voice)]
    if has_audio and keep_sound:
        filters=source_video+';[0:a]volume=0.10[bg-a];[bg-a][1:a]amix=inputs=2:duration=longest:dropout_transition=0,aresample=async=1:first_pts=0,alimiter=limit=0.95[aout]'
        out=['-map','[vout]','-map','[aout]']
    else:
        filters=source_video
        out=['-map','[vout]','-map','1:a:0']
    ffmpeg_run(inp+['-filter_complex',filters]+out+['-t',f'{duration:.3f}',
               '-c:v','libx264','-preset','ultrafast','-crf','23','-threads','1',
               '-x264-params','ref=1:bframes=0:rc-lookahead=0:sync-lookahead=0',
               '-r','30','-fps_mode','cfr','-pix_fmt','yuv420p','-g','30',
               '-c:a','aac','-b:a','112k','-ar','44100','-ac','2','-movflags','+faststart',str(dest)],timeout=200)
    # A 90-110 ms cut still contains 3 valid frames at 30 fps. The previous
    # fixed .12-second probe rejected such playable MP4 parts around 80%.
    # Validate relative to the requested cut length rather than a fixed floor.
    expected_min = min(.12, max(.067, float(duration) * .70))
    if not media_ok(dest, expected_min):
        raise RuntimeError(
            f'ส่วนวิดีโอที่ตัดต่อไม่สมบูรณ์: ช็อตที่ {float(start):.3f} วินาที '
            f'ความยาว {float(duration):.3f} วินาที (ตรวจขั้นต่ำ {expected_min:.3f})')


def render_timeline(ns,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots):
    folder=Path(folder)
    cuts_file=folder/'timeline-v11.json'
    cuts=read_json(cuts_file)
    if cuts is None:
        cuts=time_beats(beats,voice_duration,source_duration,shots)
        atom_json(cuts_file,cuts)
    outputs=[]
    for i,s in enumerate(cuts):
        output=folder/f'v11_part_{i:03}.mp4'
        if not media_ok(output, min(.12, max(.067, float(s['duration']) * .70))):
            tmp=folder/f'v11_part_{i:03}.tmp.mp4'
            ass=folder/f'v11_caption_{i:03}.ass'
            write_ass(s['caption'],s['duration'],ass)
            render_one(source,voice,tmp,ass,s,source_audio,opts.get('keep_sound',True))
            os.replace(tmp,output)
        outputs.append(output)
        ns['notify'](jid,65+int(28*(i+1)/len(cuts)),f'ตัดต่อภาพจริงพร้อมซับไทย {i+1}/{len(cuts)} ช็อต')
    manifest=folder/'v11_concat.txt'
    manifest.write_text(''.join("file '"+p.name+"'\n" for p in outputs),'utf-8')
    final=folder/'result.mp4'
    if not media_ok(final,.5):
        tmp=folder/'v11_combined.tmp.mp4'
        ffmpeg_run(['-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(tmp)],timeout=180)
        if not media_ok(tmp,.5):raise RuntimeError('รวมไฟล์วิดีโอไม่สมบูรณ์')
        tmp.replace(final)

    # Normalize only when the joined video differs from CFR 30.
    checked = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=avg_frame_rate',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(final)],
        capture_output=True, text=True, timeout=25)

    if checked.returncode or checked.stdout.strip() != '30/1':
        normalized = folder / 'v17_cfr30.tmp.mp4'
        ffmpeg_run([
            '-i', str(final),
            '-map', '0:v:0',
            '-map', '0:a:0?',
            '-vf', 'fps=30,setpts=N/(30*TB)',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-threads', '1',
            '-pix_fmt', 'yuv420p',
            '-r', '30',
            '-fps_mode', 'cfr',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(normalized)
        ], timeout=900)

        if not media_ok(normalized, .5):
            raise RuntimeError('CFR normalization failed')

        normalized.replace(final)

        check2 = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=avg_frame_rate',
             '-of', 'default=noprint_wrappers=1:nokey=1',
             str(final)],
            capture_output=True, text=True, timeout=25)

        if check2.returncode or check2.stdout.strip() != '30/1':
            raise RuntimeError('Output is not constant 30 FPS')
    # Transcript metadata; captions are already embedded directly in segment bitstreams.
    srt=folder/'captions.srt'
    if not srt.exists():
        def fmt(x):
            t=round(x*1000);return f'{t//3600000:02}:{t//60000%60:02}:{t//1000%60:02},{t%1000:03}'
        srt.write_text('\n'.join(f"{i+1}\n{fmt(x['voice_start'])} --> {fmt(x['voice_start']+x['duration'])}\n{x['caption']}\n" for i,x in enumerate(cuts)),encoding='utf-8')
    cover=folder/'cover.jpg'
    if not cover.exists():ffmpeg_run(['-ss','0.5','-i',str(final),'-frames:v','1','-q:v','4',str(cover)],timeout=30)
    return final


def install(ns):
    if ns.get('_V11_INSTALLED'):return
    ns['_V11_INSTALLED']=True
    ns['APP_VERSION']=VERSION
    ns['app'].state.v11_semantic_grounded=True
    ns['app'].state.output_size=[720,1280]
    ns['app'].state.checkpoint_storage='local_ephemeral'
    local_lock=ns['lock']
    def pipeline(jid,src_path,link,key,opts):
        folder=ns['WORK']/jid
        with local_lock:
            if jid in ns['jobs']:
                ns['jobs'][jid]['state']='working';ns['save_job'](jid)
        stage='starting'
        try:
            atom_json(folder/'args-v11.json',{'source':str(src_path),'opts':opts})
            if not src_path or link:raise RuntimeError('V11 ใช้ไฟล์ต้นฉบับที่อัปโหลดเท่านั้น')
            source=Path(src_path)
            if not source.is_file():raise RuntimeError('ไม่พบไฟล์ต้นฉบับ อาจเกิดจากเซิร์ฟเวอร์รีสตาร์ต')
            duration,source_audio=ns['probe'](source)
            stage='PROXY';ns['notify'](jid,9,'กำลังสร้างวิดีโอขนาดเล็กสำหรับวิเคราะห์')
            proxy=make_proxy(source,folder/'analysis_proxy.mp4')
            stage='SCENES';ns['notify'](jid,15,'ตรวจจับฉากและจุดตัดในวิดีโอจริง')
            shotsfile=folder/'shots-v11.json'
            shots=read_json(shotsfile)
            if not shots:
                shots=detect_shots(proxy,duration);atom_json(shotsfile,shots)
            stage='SCRIPT';ns['notify'](jid,27,'Gemini วิเคราะห์ภาพและจับคู่บทพากย์กับฉาก')
            afile=folder/'analysis-v11.json'
            analysis=read_json(afile)
            if not analysis:
                # Save the *raw* Gemini result before local semantic/time budget
                # validation. If normalization fails, resume MUST NOT repay the
                # user's 20-per-day quota for the same completed analysis.
                raw_file=folder/'analysis-raw-v17.json'
                raw_analysis=read_json(raw_file)
                if not raw_analysis:
                    import httpx
                    with httpx.Client(timeout=httpx.Timeout(540,connect=20,read=540,write=540,pool=20)) as client:
                        raw_analysis=analyze_proxy(ns,client,proxy,key,duration,shots,opts['length'],opts['tone'])
                    atom_json(raw_file,raw_analysis)
                analysis=normalize_beats(raw_analysis,shots,duration)
                atom_json(afile,analysis)
            stage='VOICE';ns['notify'](jid,51,'สร้างเสียงพากย์ภาษาไทยจากบทที่ตรงกับภาพ')
            wav=folder/'voice.wav'
            if wav.exists() and media_ok(wav,1,expect_video=False):
                voiceduration=duration_of(wav)
            else:
                import httpx
                with httpx.Client(timeout=httpx.Timeout(540,connect=20,read=540,write=540,pool=20)) as client:
                    voiceduration=ns['tts'](client,analysis['script'],key,opts['voice'],wav)
            (folder/'script.txt').write_text(analysis.get('title','')+'\n\n'+analysis.get('summary','')+'\n\n'+analysis['script'],encoding='utf-8')
            stage='MATCH';ns['notify'](jid,63,'จัดเรียงฉากให้ตรงกับประโยคพากย์')
            stage='RENDER'
            output=render_timeline(ns,jid,source,wav,folder,analysis['beats'],duration,source_audio,voiceduration,opts,shots)
            stage='VERIFY'
            if not media_ok(output,1):raise RuntimeError('ไฟล์ MP4 ปลายทางเสียหาย')
            with local_lock:
                ns['jobs'][jid].update(state='done',progress=100,step='ตัดต่อสำเร็จ พร้อมดาวน์โหลด MP4',error=None,
                                           title=analysis.get('title','สรุปเรื่องราวจากภาพจริง'),
                                           summary=analysis.get('summary',''),script=analysis['script'],
                                           seconds=round(duration_of(output),2),mode='original',
                                           mode_note='ภาพวิดีโอต้นฉบับ ตัดต่อตามเนื้อหาที่ AI วิเคราะห์')
                ns['save_job'](jid)
        except Exception as exc:
            with local_lock:
                if jid in ns['jobs']:
                    message=str(exc).replace(key,'[key redacted]') if key else str(exc)
                    ns['jobs'][jid].update(state='error',step=f'ล้มเหลวที่ขั้นตอน {stage}',error=message[:700])
                    ns['save_job'](jid)
        finally:
            # NEVER delete source or complete checkpoints here. Cleanup TTL manages expired jobs.
            pass
    ns['process']=pipeline
    from fastapi import Form, HTTPException
    import secrets
    @ns['app'].post('/api/jobs/{jid}/resume')
    def resume(jid: str, token: str, api_key: str = Form('')):
        with local_lock:
            job=ns['jobs'].get(jid)
            if not job or not secrets.compare_digest(job.get('token',''),token):
                raise HTTPException(404,'ไม่พบงานนี้ หรือโทเค็นไม่ถูกต้อง')
            if job.get('state') not in ('error','interrupted'):
                raise HTTPException(409,'เริ่มต่อได้เฉพาะงานที่มีข้อผิดพลาดหรือถูกขัดจังหวะ')
            if len(api_key.strip()) < 12:raise HTTPException(400,'กรุณาระบุ Gemini API Key')
            args=read_json(ns['WORK']/jid/'args-v11.json')
            if not args or not Path(args.get('source','')).is_file():
                raise HTTPException(410,'ไฟล์งานถูกล้างจาก Render แล้ว กรุณาอัปโหลดอีกครั้ง')
            job.update(state='queued',step='กำลังเริ่มต่อจากขั้นตอนที่บันทึกไว้',error=None)
            ns['save_job'](jid)
            ns['executor'].submit(ns['process'],jid,args['source'],'',api_key.strip(),args['opts'])
        return {'id':jid,'state':'queued','resumed':True}
    @ns['app'].get('/api/v11/info')
    def info():
        return {'version':VERSION,'semantic_matching':True,'shot_detection':True,'analysis_proxy':True,
                'source_footage_only':True,'resolution':[WIDTH,HEIGHT],'fps':FPS,
                'checkpoints':'local ephemeral (not durable on Render free restarts)',
                'render_threads':1,'requires_uploaded_video':True}
