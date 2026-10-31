"""V20: resource-limited analysis proxy with input-keyframe-first decoding.

Only the Gemini analysis proxy is reduced; final cuts still use the original
uploaded video at full quality. No Gemini calls occur in this module.
"""
from __future__ import annotations
import os
from pathlib import Path

VERSION = 'v20-adaptive-proxy-2026-10-31'


def proxy_profiles(seconds):
    """Cheap profiles first, with a more conservative fallback on failure."""
    if seconds > 180:
        return [(True, 2, 384, 360), (True, 1, 320, 240)]
    if seconds > 60:
        return [(True, 4, 480, 300), (True, 2, 384, 210)]
    return [(False, 6, 512, 240), (True, 3, 384, 150)]


def make_proxy(source, dest):
    import v11
    source, dest = Path(source), Path(dest)
    if v11.media_ok(dest, 1):
        return dest
    if not source.is_file():
        raise RuntimeError('ไม่พบไฟล์ต้นฉบับสำหรับสร้าง PROXY')
    duration = v11.duration_of(source)
    if not (1 <= duration <= 24 * 3600):
        raise RuntimeError('ความยาวต้นฉบับไม่ถูกต้องหรือยาวเกินขอบเขตของบริการ')
    errors=[]
    for fast_seek, fps, max_side, timeout in proxy_profiles(duration):
        tmp=dest.with_name(dest.stem + '.v20.tmp.mp4')
        tmp.unlink(missing_ok=True)
        args=[]
        if fast_seek:
            # Decode only intra/key frames for analysis. Filter restores a
            # constant-rate timeline, preserving the original timestamps.
            args+=['-skip_frame','nokey']
        args+=['-i',str(source),'-map','0:v:0','-map','0:a:0?',
               '-vf',(f'fps={fps},'
                      f'scale={max_side}:{max_side}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                      f'format=yuv420p,tpad=stop_mode=clone:stop_duration=12,trim=duration={duration:.4f}'),
               '-c:v','libx264','-preset','ultrafast','-crf','33','-threads','1',
               '-c:a','aac','-ac','1','-ar','16000','-b:a','24k',
               '-max_muxing_queue_size','1024','-movflags','+faststart',str(tmp)]
        try:
            v11.ffmpeg_run(args,timeout=timeout)
            if not v11.media_ok(tmp,1):
                raise RuntimeError('PROXY MP4 ที่ FFmpeg สร้างไม่สมบูรณ์')
            converted=v11.duration_of(tmp)
            if abs(converted-duration)>max(5.0, duration*0.002):
                raise RuntimeError(f'ความยาว PROXY ไม่ตรงต้นฉบับ ({converted:.2f}/{duration:.2f} วินาที)')
            os.replace(tmp,dest)
            return dest
        except (RuntimeError, OSError) as exc:
            errors.append(str(exc)[-140:])
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError('สร้าง PROXY ไม่สำเร็จบนเซิร์ฟเวอร์ปัจจุบัน (ไม่เรียก Gemini): '
                       'ต้นฉบับอาจยาวหรือเข้ารหัสหนักเกินกำลัง Render Free; '
                       'แนะนำตัดเป็นช่วงสั้นลงหรือแปลงต้นฉบับเป็น H.264 1080p ก่อนอัปโหลด '
                       '[FFmpeg: '+(' / '.join(errors))[-240:]+']')


def install(ns):
    if ns.get('_V20_PROXY_INSTALLED'):
        return
    import v11
    v11.make_proxy = make_proxy
    ns['_V20_PROXY_INSTALLED'] = True
    ns['APP_VERSION'] = VERSION
    ns['app'].state.v20_adaptive_proxy = True
    @ns['app'].get('/api/v20/info')
    def info():
        return {'version':VERSION, 'proxy_only':True,
                'source_video_untouched':True,'gemini_calls_for_proxy':0,
                'keyframe_decode_for_long_source':True,
                'checkpoints': 'proxy can be reused while local files persist'}
