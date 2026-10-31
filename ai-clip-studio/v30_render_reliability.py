"""V30 frame-accurate finalization and idempotent resume.

Repairs only small (<0.25 second) frame-count drift by interpolating frames
between source frames. Never invent or repeat shots and never repeat TTS calls.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import subprocess

VERSION = 'v30-verified-render-reliability-2026-10-31'
TARGETS = (60, 90, 120)


def media_info(path):
    q=subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=nb_frames,avg_frame_rate:format=duration',
        '-of','json',str(path)],capture_output=True,text=True,timeout=40)
    if q.returncode or not q.stdout:
        raise RuntimeError('ตรวจข้อมูลเฟรม MP4 ไม่สำเร็จ')
    doc=json.loads(q.stdout)
    stream=doc.get('streams') or []
    if len(stream)!=1:
        raise RuntimeError('ไฟล์ MP4 ไม่มีภาพวิดีโอที่ตรวจสอบได้')
    frame=int(stream[0].get('nb_frames') or 0)
    duration=float(doc.get('format',{}).get('duration') or 0)
    return frame, stream[0].get('avg_frame_rate'),duration


def exact_media(path,target):
    path=Path(path)
    if not path.is_file() or target not in TARGETS:return False
    try:
        n,fps,duration=media_info(path)
        if n!=target*30 or fps!='30/1' or abs(duration-target)>.05:
            return False
        q=subprocess.run(['ffprobe','-v','error','-select_streams','a:0',
            '-show_entries','stream=codec_type','-of','csv=p=0',str(path)],
            capture_output=True,text=True,timeout=20)
        return q.returncode==0 and 'audio' in q.stdout
    except (OSError,ValueError,RuntimeError,TypeError,subprocess.TimeoutExpired):
        return False


def finalize_frames(source,target):
    source=Path(source)
    expected=target*30
    if exact_media(source,target):return source
    frames,fps,seconds=media_info(source)
    if target not in TARGETS or fps!='30/1' or not math.isfinite(seconds):
        raise RuntimeError('รูปแบบวิดีโอหรือความยาวไม่ตรงกับงานที่เลือก')
    drift=expected-frames
    if frames<=0 or abs(drift)>6 or abs(seconds-target)>.30:
        raise RuntimeError(f'เฟรมวิดีโอ {frames}/{expected} ผิดปกติเกินกว่าจะซ่อมโดยไม่วนฉาก')
    temp=source.with_name('v30_exact_frames.tmp.mp4')
    temp.unlink(missing_ok=True)
    # Motion-blend interpolation covers only tiny natural frame-rounding drift.
    # The +2 compensates for minterpolate lookahead at EOF (validated by ffprobe).
    if drift>0:
        vf=(f'setpts=(PTS-STARTPTS)*{expected+2}/{frames},'
            f'minterpolate=fps=30:mi_mode=blend,trim=end_frame={expected},'
            'setpts=N/(30*TB),fps=30')
    else:
        vf=f'trim=end_frame={expected},setpts=N/(30*TB),fps=30'
    filters=(f'[0:v]{vf}[v];'
             f'[0:a]aresample=async=1:first_pts=0,'
             f'apad=whole_dur={target},atrim=duration={target},asetpts=PTS-STARTPTS[a]')
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source),
         '-filter_complex',filters,'-map','[v]','-map','[a]',
         '-c:v','libx264','-preset','ultrafast','-crf','23','-threads','1',
         '-r','30','-fps_mode','cfr','-pix_fmt','yuv420p','-g','30',
         '-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-t',str(target),
         '-movflags','+faststart',str(temp)]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=1150)
        if p.returncode:
            raise RuntimeError('ซ่อมเฟรม MP4 ไม่สำเร็จ: '+p.stderr[-500:])
        if not exact_media(temp,target):
            frames_after,_,_ = media_info(temp)
            raise RuntimeError(f'ซ่อมเฟรมแล้วได้ {frames_after}/{expected} เฟรม')
        temp.replace(source)
        return source
    finally:
        temp.unlink(missing_ok=True)


def install(ns):
    if ns.get('_V30_RENDER_RELIABILITY_INSTALLED'):return
    import v11
    previous_render=v11.render_timeline
    def verified_render(ns1,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots):
        target=int(opts.get('length',60))
        file=Path(folder)/'result.mp4'
        # A completed checkpoint must NEVER be re-muxed. For example V21
        # used to mix old narration a second time on resume.
        if (target in TARGETS and (Path(folder)/'v21_success.marker').exists()
                and exact_media(file,target)):
            return file
        rendered=previous_render(ns1,jid,source,voice,folder,beats,source_duration,
                                  source_audio,voice_duration,opts,shots)
        if target in TARGETS and 'length' in opts:
            return finalize_frames(rendered,target)
        return rendered
    v11.render_timeline=verified_render
    ns['_V30_RENDER_RELIABILITY_INSTALLED']=True
    ns['app'].state.v30_render_reliability=True
    @ns['app'].get('/api/v30/render-check')
    def info():
        return {'version':VERSION,'fps':30,'durations':[60,90,120],
                'max_corrected_frames':6,'interpolate_not_loop':True,
                'completed_job_resume_uses_valid_video':True}
