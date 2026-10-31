"""V15: exactly 1800 CFR frames for 60-second editorial videos.

A duration choice is a contract, not an approximate Gemini prompt. We synchronize
narration conservatively, reuse only source-grounded shots via V14/V12, then
verify the exported MP4. No extra Gemini API calls.
"""
from __future__ import annotations
import threading
from pathlib import Path
import subprocess

VERSION='v17-60-second-voice-quota-safe-2026-10-31'
TARGET=60.0
FPS=30
FRAME_COUNT=1800
MIN_SPEECH=46.0
MAX_SPEECH=85.0


def _voice_duration(source):
    import v11
    return v11.duration_of(source)


def ensure_voice_60(wav):
    """Audio-duration correction with 0.80x..1.45x pitch-preserving speech tempo.

    Short tail <= 2.5s is room tone rather than long silence. Reject clips
    requiring severe speech stretching or chopping words off the end.
    """
    import v11
    wav=Path(wav)
    duration=_voice_duration(wav)
    if abs(duration-TARGET)<0.018:
        return TARGET
    if not (MIN_SPEECH <= duration <= MAX_SPEECH):
        raise RuntimeError(
            'เสียงพากย์ยาว '+str(round(duration,1))+' วินาที ไม่พอดีสำหรับคลิป 60 วินาที '
            '(ต้องอยู่ประมาณ 46–85 วินาที) เพื่อไม่ให้เสียงเร็วหรือช้าจนผิดธรรมชาติ '
            'กรุณาใช้วิดีโอที่มีเนื้อหามากขึ้นหรือปรับบทให้เหมาะกับหนึ่งนาที')
    # One TTS call only. If Gemini spoke 78.7 seconds (real observed case),
    # FFmpeg atempo=1.328 safely brings the already-generated WAV to 59.25s.
    # No paid retries or destructive cropping of words.
    speed=min(1.45,max(0.80,duration/59.25))
    stretched=duration/speed
    if stretched>60.10 or stretched<57.50:
        raise RuntimeError('เสียงพากย์ที่สร้างมาสั้นหรือยาวเกินไปสำหรับหนึ่งนาทีโดยไม่เร่งหรือยืดเสียงผิดธรรมชาติ')
    temp=wav.with_name('v15_voice_60.tmp.wav')
    v11.ffmpeg_run(['-i',str(wav),'-af',
         f'atempo={speed:.9f},aresample=48000,apad=whole_dur=60,atrim=duration=60,asetpts=PTS-STARTPTS',
         '-ac','1','-c:a','pcm_s16le',str(temp)],timeout=90)
    if abs(_voice_duration(temp)-TARGET)>.018:
        temp.unlink(missing_ok=True)
        raise RuntimeError('ปรับความยาวเสียงพากย์เป็น 60 วินาทีไม่สำเร็จ')
    temp.replace(wav)
    return TARGET


def _frame_count(path):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=nb_frames','-of','default=noprint_wrappers=1:nokey=1',
        str(path)],capture_output=True,text=True,timeout=20)
    try:return int(p.stdout.strip()) if p.returncode==0 else 0
    except ValueError:return 0


def finalize_mp4_60(raw, final):
    """Finalize the source-grounded edit to 1800 frames and 60s audio.

    Stream-copy video when possible; full transcode only for boundary drift.
    Only tolerate 0.75 seconds of video underrun: never freeze a long outro.
    """
    import v11
    raw=Path(raw);final=Path(final)
    duration=v11.duration_of(raw)
    if not (59.25<=duration<=60.75):
        raise RuntimeError(f'ผลรวมภาพกับเสียงยาว {duration:.2f} วินาที ไม่สามารถแก้ให้เป็นหนึ่งนาทีโดยไม่ทำให้ภาพค้าง')
    temp=final.with_name('v15_final.tmp.mp4')
    # Fast path: V11 segments are already H.264 30 FPS. Copy the first
    # 1800 frames directly, avoiding an expensive 2nd video encode on Render Free.
    # Re-encode only AAC to normalize the audio timeline.
    v11.ffmpeg_run(['-i',str(raw),'-map','0:v:0','-map','0:a:0',
        '-c:v','copy','-frames:v',str(FRAME_COUNT),
        '-af','aresample=async=1:first_pts=0,apad=whole_dur=60,atrim=duration=60,asetpts=PTS-STARTPTS',
        '-c:a','aac','-b:a','112k','-ar','48000','-ac','2',
        '-t','60','-movflags','+faststart',str(temp)],timeout=180)
    # If stream-copy timestamp rounding gave the wrong frame count or
    # duration, use a conservative full transcode only for those cases.
    frames=_frame_count(temp) if v11.media_ok(temp,59.0) else 0
    if frames!=FRAME_COUNT or abs(v11.duration_of(temp)-TARGET)>.05:
        filter_video=f'[0:v]fps={FPS},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={FRAME_COUNT},setpts=PTS-STARTPTS,format=yuv420p[v]'
        filter_audio='[0:a]aresample=async=1:first_pts=0,apad=whole_dur=60,atrim=duration=60,asetpts=PTS-STARTPTS[a]'
        v11.ffmpeg_run(['-i',str(raw),'-filter_complex',filter_video+';'+filter_audio,
            '-map','[v]','-map','[a]',
            '-c:v','libx264','-preset','ultrafast','-crf','23',
            '-threads','1','-r',str(FPS),'-fps_mode','cfr','-pix_fmt','yuv420p',
            '-g','30','-c:a','aac','-b:a','112k','-ar','48000','-ac','2',
            '-t','60','-movflags','+faststart',str(temp)],timeout=800)
    if not v11.media_ok(temp,59.0):
        raise RuntimeError('ไฟล์หนึ่งนาทีที่ปรับความยาวไม่สมบูรณ์')
    p=subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
         '-show_entries','stream=nb_frames,avg_frame_rate',
         '-of','default=noprint_wrappers=1',str(temp)],capture_output=True,text=True,timeout=20)
    if p.returncode!=0 or f'nb_frames={FRAME_COUNT}' not in p.stdout or 'avg_frame_rate=30/1' not in p.stdout:
        raise RuntimeError('ส่งออกวิดีโอ 1800 เฟรมที่ 30 FPS ไม่สำเร็จ')
    if abs(v11.duration_of(temp)-60.0)>.05:
        raise RuntimeError('วิดีโอที่ส่งออกไม่ยาว 60.00 วินาทีตามที่กำหนด')
    temp.replace(final)
    return final


def install(ns):
    if ns.get('_V15_INSTALLED'):
        return
    import v11
    import v14_semantic
    original_tts=ns['tts']
    original_render=v11.render_timeline
    original_process=ns['process']
    original_prompt=v14_semantic.make_prompt
    current=threading.local()
    def prompt_60(timecodes,length,tone):
        prompt=original_prompt(timecodes,length,tone)
        if int(length)==60:
            prompt+=(
                ' EXACT ONE-MINUTE EDITORIAL NARRATION. Aim for 56-63 seconds spoken Thai '
                'at a natural comfortable pace (around 445-535 Thai characters), '
                'roughly 8-13 concise evidence-backed narration beats with interesting '
                'hook, development, and clear conclusion. Favor detail that ACTUALLY APPEARS '
                'in source, and never invent claims or match unrelated images merely to reach time.'
            )
        return prompt
    def process_60(jid,src_path,link,key,opts):
        current.target=int(opts.get('length',30))
        try:
            if current.target==60 and src_path:
                try:
                    seconds,_=ns['probe'](Path(src_path))
                    if seconds < 35:
                        raise RuntimeError(
                            'ต้นฉบับยาวไม่ถึง 35 วินาที จึงไม่เหมาะทำคลิป 60 วินาทีแบบภาพไม่ซ้ำ '
                            'กรุณาเพิ่มวิดีโอที่เกี่ยวข้อง เพื่อไม่ให้ตัดต่อแล้วดูวนซ้ำหรือกระตุก')
                except Exception as exc:
                    with ns['lock']:
                        if jid in ns['jobs']:
                            ns['jobs'][jid].update(state='error',progress=0,
                                step='ตรวจความยาวต้นฉบับ',error=str(exc)[:600])
                            ns['save_job'](jid)
                    return
            return original_process(jid,src_path,link,key,opts)
        finally:
            current.target=None
    def tts_60(client,script,key,voice,wav):
        # The paid TTS request is made once, not retried for exact length.
        duration=original_tts(client,script,key,voice,wav)
        return ensure_voice_60(wav) if getattr(current,'target',None)==60 else duration
    def render_60(ns1,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots):
        if int(opts.get('length',30))!=60:
            return original_render(ns1,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots)
        # Also normalize older checkpoints resumed from a failure.
        voice_duration=ensure_voice_60(voice)
        folder=Path(folder)
        result=folder/'result.mp4'
        # Render V11/V12 to a separate path first so the final file is not
        # accidentally treated as a valid cached full-minute artifact.
        if result.exists() and v11.media_ok(result,59.95) and abs(v11.duration_of(result)-TARGET)<.05:
            return result
        result.unlink(missing_ok=True)
        raw=original_render(ns1,jid,source,voice,folder,beats,source_duration,source_audio,voice_duration,opts,shots)
        staged=folder/'v15_raw_edit.mp4'
        Path(raw).replace(staged)
        return finalize_mp4_60(staged,result)
    ns['tts']=tts_60
    ns['process']=process_60
    v14_semantic.make_prompt=prompt_60
    v11.render_timeline=render_60
    ns['app'].state.v15_exact_minute=True
    ns['APP_VERSION']=VERSION
    ns['_V15_INSTALLED']=True
    @ns['app'].get('/api/v15/info')
    def info():
        return {'version':VERSION,'default_duration_seconds':60,'exact_duration_seconds':60,
                'fps':30,'frames':FRAME_COUNT,'extra_gemini_requests':0,
                'speech_speed_limits':[0.80,1.45],
                'check':'ffprobe validates video frames and final media duration'}
