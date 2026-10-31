"""FFmpeg regressions for valid sub-120 ms editorial source cuts."""
import subprocess
import json
import v11


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    assert p.returncode == 0, p.stderr[-1000:]
    return p.stdout


def sources(tmp_path):
    src=tmp_path/'source.mp4';wav=tmp_path/'voice.wav'
    run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=3',
         '-f','lavfi','-i','sine=frequency=330:sample_rate=24000:duration=3',
         '-threads','1','-c:v','libx264','-preset','ultrafast',
         '-pix_fmt','yuv420p','-c:a','aac',str(src)])
    run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=3',
         '-c:a','pcm_s16le',str(wav)])
    return src,wav


def test_90_100_110ms_valid_segments(tmp_path):
    src,wav=sources(tmp_path)
    ass=tmp_path/'part.ass'
    for d in (.09,.10,.11,.12):
        dst=tmp_path/f'part_{d}.mp4'
        v11.write_ass('ฉากที่เกี่ยวข้อง',d,ass)
        v11.render_one(src,wav,dst,ass,{'source_start':.15,'voice_start':.15,'duration':d},True,True)
        assert v11.media_ok(dst,min(.12,max(.067,d*.7)))
        s=json.loads(run(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
                            '-show_entries','stream=nb_read_frames','-of','json',str(dst)]))
        assert int(s['streams'][0]['nb_read_frames']) >= 2


def test_render_timeline_accepts_100ms_cut_and_checkpoint(tmp_path):
    src,wav=sources(tmp_path)
    shots=[{'id':'first','start':0,'end':2.9}]
    cuts=[{'source_start':0.,'duration':.1,'voice_start':0.,'caption':'ต้นฉบับ','text':'ต้นฉบับ','shot_id':'first'},
          {'source_start':.1,'duration':1.4,'voice_start':.1,'caption':'เหตุการณ์','text':'เหตุการณ์','shot_id':'first'}]
    v11.atom_json(tmp_path/'timeline-v11.json', cuts)
    ns={'notify':lambda *a:None}
    out=v11.render_timeline(ns,'test',src,wav,tmp_path,[],3.,True,1.5,{'keep_sound':True},shots)
    assert v11.media_ok(out,1.4)
    a=tmp_path/'v11_part_000.mp4'
    old=a.stat().st_mtime_ns
    assert v11.render_timeline(ns,'test',src,wav,tmp_path,[],3.,True,1.5,{'keep_sound':True},shots)==out
    assert a.stat().st_mtime_ns==old
