"""AI Clip Studio V9: source-footage-first editorial 9:16 output.
This replaces letterboxing and looping footage with a dark-caption-panel layout.
"""
import json
import math
import re
import unicodedata
from pathlib import Path


def _safe_ass(s):
    return (str(s).replace('\\', '').replace('{', '').replace('}', '')
            .replace('\n', ' ').replace('\r', ' ').replace('\u2028', ' ').strip())


def _thai_clusters(s):
    clusters=[]
    for c in s:
        if clusters and (unicodedata.combining(c) or c in '\u0e31\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39\u0e47\u0e48\u0e49\u0e4a\u0e4b\u0e4c\u0e4d'):
            clusters[-1] += c
        else:
            clusters.append(c)
    return clusters


def _caption_two_lines(s):
    clusters=_thai_clusters(_safe_ass(s)[:72])
    if not clusters:
        return '', ''
    if len(clusters) <= 12:
        return ''.join(clusters), ''
    aim=int(len(clusters)*.58)
    spaces=[i for i in range(max(5,aim-9),min(len(clusters)-4,aim+9)) if clusters[i]==' ']
    cut=min(spaces,key=lambda i:abs(i-aim)) if spaces else aim
    return ''.join(clusters[:cut]).strip(), ''.join(clusters[cut:]).strip()


def _ass_time(seconds):
    cs=round(max(0.,seconds)*100)
    return f'{cs//360000:01}:{(cs//6000)%60:02}:{(cs//100)%60:02}.{cs%100:02}'


def editorial_ass(captions, seconds, outfile):
    text=[_safe_ass(s) for s in (captions or []) if _safe_ass(s)]
    if not text:
        return False
    # ASS uses BGR colors. Yellow &H0000FFFF; white &H00FFFFFF.
    preamble='''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Story,Noto Sans Thai,51,&H00FFFFFF,&H0000FFFF,&H00090E10,&H70000000,-1,0,0,0,100,100,0,0,1,3,2,2,45,45,115,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    total=float(seconds)
    with Path(outfile).open('w',encoding='utf-8') as f:
        f.write(preamble)
        for i,cap in enumerate(text):
            a,b=_caption_two_lines(cap)
            # Avoid corrupting ASS events with special control sequences.
            top='{\\c&HFFFFFF&}'+a
            bottom=('\\N{\\c&H00FFFF&}'+b) if b else ''
            start,end=total*i/len(text),total*(i+1)/len(text)
            f.write(f'Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Story,,0,0,0,,{{\\fad(120,100)}}{top}{bottom}\n')
    return True


def smart_shots(highlights, source_seconds, voice_seconds):
    """Cut chronological source intervals once before reusing any footage."""
    dur=max(.5,float(source_seconds));target=max(.4,float(voice_seconds))
    important=[]
    for h in (highlights or [])[:24]:
        try:
            start=max(0.,min(float(h['start']),dur-.4))
            end=max(start+.4,min(float(h['end']),dur))
            if end>start+.45:
                while start<end-.4:
                    span=min(3.6,end-start)
                    important.append((start,span))
                    start+=span
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    important.sort()
    chosen=[]
    def add_segment(start,span):
        nonlocal chosen
        end=min(dur,start+span)
        # Subtract any already-used time, so there is no replay on long videos.
        uncovered=[(start,end)]
        for a,b in chosen:
            next_intervals=[]
            for x,y in uncovered:
                if b<=x or a>=y:next_intervals.append((x,y))
                else:
                    if a-x>.45:next_intervals.append((x,a))
                    if y-b>.45:next_intervals.append((b,y))
            uncovered=next_intervals
        for x,y in uncovered:
            if y-x>.45:chosen.append((x,y))
    for s,span in important:
        add_segment(s,span)
    used=sum(b-a for a,b in chosen)
    if used<target:
        taken=sorted(chosen)
        gaps=[];cursor=0.
        for a,b in taken:
            if a-cursor>.45:gaps.append((cursor,a))
            cursor=max(cursor,b)
        if dur-cursor>.45:gaps.append((cursor,dur))
        for a,b in gaps:
            while a<b-.45 and used<target:
                span=min(3.4,b-a,target-used)
                if span<.45:break
                chosen.append((a,a+span));used+=span;a+=span
    chosen.sort()
    total=0.; result=[]
    for a,b in chosen:
        if total>=target-.1:break
        remaining=target-total
        span=min(b-a,remaining)
        if span>.3:
            result.append((a,span));total+=span
    # Only exceptionally short source videos need a replay. Never silently loop 5 shots over and over.
    if total<target-.4 and dur<target:
        while total<target-.2 and len(result)<45:
            left=target-total
            s=(len(result)*3.1)%max(.5,dur-.5)
            span=min(2.7,left,dur-s)
            if span<.4:break
            result.append((s,span));total+=span
    return result


def install(ns):
    run=ns['run'];notify=ns['notify'];probe=ns['probe']
    original_analyze=ns['analyze']
    def analyze_with_hook(client,path,key,duration,length,tone):
        improved=(str(tone)+'; Start with a strong factual hook, explain events in clear chronological order. '
                  'Choose actual action moments, 10-18 precise captions no more than 25 Thai characters each, '
                  'and meaningful non-repeating highlight ranges with realistic source timestamps. '
                  'Do not invent scenes, reactions, quotations or people.')
        return original_analyze(client,path,key,duration,length,improved)

    def editorial_render(jid,src,audio,source_duration,source_audio,voice_duration,analysis,opts,folder):
        folder=Path(folder)
        aspect=opts.get('aspect','9:16')
        if aspect!='9:16':
            # Reuse the original widescreen pipeline for landscape requests.
            return previous_render(jid,src,audio,source_duration,source_audio,voice_duration,analysis,opts,folder)
        metadata=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(src)],25))
        stream=metadata.get('streams',[{}])[0]
        portrait=int(stream.get('height',0))>int(stream.get('width',0))
        # Portrait sources fill the whole top scene; landscape sources fit in a blurred extension.
        if portrait:
            foreground='scale=720:910:force_original_aspect_ratio=increase,crop=720:910'
        else:
            foreground='scale=720:910:force_original_aspect_ratio=decrease'
        filt=(
          '[0:v]split=2[bg][fg];'
          '[bg]scale=144:182:force_original_aspect_ratio=increase,crop=144:182,'
          'boxblur=8:1,scale=720:910,eq=brightness=-0.20[blur];'
          f'[fg]{foreground},eq=contrast=1.05:saturation=1.06[sharp];'
          '[blur][sharp]overlay=(W-w)/2:(H-h)/2:shortest=1,'
          'pad=720:1280:0:0:color=0x121b20,'
          'drawbox=x=0:y=910:w=720:h=370:color=0x152123:t=fill,'
          'fps=30,format=yuv420p,setsar=1[vout]')
        chunks=smart_shots(analysis.get('highlights',[]),source_duration,voice_duration)
        if not chunks or sum(d for _,d in chunks)<voice_duration*.94:
            raise RuntimeError('วิดีโอต้นฉบับสั้นเกินไปสำหรับบทพากย์ หรือไม่สามารถตัดต่อได้ครบความยาว')
        parts=[]
        for i,(start,span) in enumerate(chunks):
            dest=folder/f'seg_{i:02}.mp4'
            cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                 '-ss',f'{start:.3f}','-t',f'{span:.3f}','-i',str(src),
                 '-filter_complex',filt,'-map','[vout]',
                 '-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p',
                 '-threads','2']
            if source_audio and opts.get('keep_sound'):
                cmd += ['-map','0:a:0','-c:a','aac','-b:a','96k','-ar','44100','-ac','2']
            else:
                cmd += ['-an']
            cmd.append(str(dest))
            run(cmd,180);parts.append(dest)
            if i%2==0:
                notify(jid,67+int(17*(i+1)/len(chunks)),f'จัดเฟรมภาพจริงและตัดต่อช็อต {i+1}/{len(chunks)}')
        manifest=folder/'concat.txt'
        manifest.write_text(''.join("file '"+p.name+"'\n" for p in parts),'utf-8')
        montage=folder/'montage.mp4'
        run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(manifest),'-c','copy',str(montage)],180)
        subtitle=folder/'editorial.ass'
        has_subs=bool(opts.get('captions')) and editorial_ass(analysis.get('captions',[]),voice_duration,subtitle)
        output=folder/'result.mp4'
        args=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(montage),'-i',str(audio),
              '-t',f'{voice_duration:.3f}','-map','0:v:0']
        if source_audio and opts.get('keep_sound'):
            args += ['-filter_complex','[0:a]volume=0.13[bg];[bg][1:a]amix=inputs=2:duration=shortest:dropout_transition=0[aout]', '-map','[aout]']
        else:
            args += ['-map','1:a:0']
        if has_subs:
            args+=['-vf',f'ass={subtitle}']
        args+=['-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p',
               '-c:a','aac','-b:a','160k','-ar','44100','-ac','2',
               '-threads','2','-movflags','+faststart','-shortest',str(output)]
        run(args,300)
        run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss','0.8','-i',str(output),'-frames:v','1','-q:v','3',str(folder/'cover.jpg')],25)
        return output

    previous_render=ns['render_video']
    ns['analyze']=analyze_with_hook
    ns['render_video']=editorial_render
    ns['APP_VERSION']='v9-editorial-source-footage-2026-10-30'
    ns['app'].state.editorial_source_footage=True
