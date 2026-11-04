package com.pad6.hokhighlight;

import android.app.Activity;
import android.content.ContentValues;
import android.content.Intent;
import android.content.ContentResolver;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.graphics.Color;
import android.media.MediaMetadataRetriever;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.StatFs;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.VideoView;
import android.widget.MediaController;

import androidx.media3.transformer.Effects;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.effect.Presentation;
import androidx.media3.transformer.Composition;
import androidx.media3.transformer.DefaultEncoderFactory;
import androidx.media3.transformer.EditedMediaItem;
import androidx.media3.transformer.EditedMediaItemSequence;
import androidx.media3.transformer.ExportException;
import androidx.media3.transformer.ExportResult;
import androidx.media3.transformer.ProgressHolder;
import androidx.media3.transformer.Transformer;
import androidx.media3.transformer.VideoEncoderSettings;

import com.google.common.collect.ImmutableList;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import com.google.android.gms.tasks.Tasks;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {
  private static final int PICK_VIDEO = 412;
  private static final long MAX_BYTES = 3L * 1024 * 1024 * 1024;
  private static final int BG = Color.rgb(10, 16, 30);
  private static final int TEXT = Color.rgb(243, 247, 255);
  private static final int MUTED = Color.rgb(163, 179, 199);
  private final Handler main = new Handler(Looper.getMainLooper());
  private final ExecutorService worker = Executors.newSingleThreadExecutor();
  private final AtomicBoolean stopScan = new AtomicBoolean(false);
  private final List<KillMark> marks = new ArrayList<>();

  private Uri videoUri;
  private long durationMs;
  private TextView details, status, markerCount;
  private ProgressBar progress;
  private LinearLayout markList;
  private VideoView preview;
  private EditText timeInput;
  private Button scanButton, cancelButton, exportButton;
  private Transformer transformer;
  private File outputFile;
  private boolean busy = false;
  private boolean scanning = false;

  static final class KillMark {
    long when;
    boolean enabled = true;
    String reason;
    KillMark(long when, String reason) { this.when=when; this.reason=reason; }
  }

  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    getWindow().setStatusBarColor(BG);
    getWindow().setNavigationBarColor(BG);
    buildUi();
    setStatus("พร้อมใช้งาน • เลือกคลิป HOK เพื่อเริ่ม");
  }

  private int dp(float value) { return (int)(getResources().getDisplayMetrics().density * value + .5f); }

  private TextView label(String text, int sp, int color) {
    TextView t = new TextView(this);
    t.setText(text); t.setTextSize(sp); t.setTextColor(color);
    t.setPadding(0,dp(6),0,dp(7));
    return t;
  }

  private Button button(String text, LinearLayout row, View.OnClickListener action) {
    Button b=new Button(this); b.setText(text); b.setAllCaps(false);
    row.addView(b,new LinearLayout.LayoutParams(0,dp(52),1));
    b.setOnClickListener(action); return b;
  }

  private LinearLayout row(LinearLayout parent) {
    LinearLayout l=new LinearLayout(this);
    l.setOrientation(LinearLayout.HORIZONTAL); l.setGravity(Gravity.CENTER_VERTICAL);
    parent.addView(l,new LinearLayout.LayoutParams(-1,-2));
    return l;
  }

  private void buildUi() {
    ScrollView scroller=new ScrollView(this);
    scroller.setFillViewport(true); scroller.setBackgroundColor(BG);
    LinearLayout root=new LinearLayout(this);
    root.setPadding(dp(16),dp(22),dp(16),dp(28)); root.setOrientation(LinearLayout.VERTICAL);
    scroller.addView(root);setContentView(scroller);

    root.addView(label("HOK HIGHLIGHT AI V5",26,TEXT));
    root.addView(label("ตัดไฮไลท์ 3 วินาทีก่อนคิล + 3 วินาทีหลังคิล\nทำงานในเครื่อง ไม่อัปโหลดวิดีโอขึ้นเซิร์ฟเวอร์",14,MUTED));

    LinearLayout importRow=row(root);
    button("เลือกวิดีโอ HOK",importRow,v->chooseVideo());
    button("เล่น / หยุดภาพ",importRow,v->{
      if(videoUri == null) return;
      if(preview.isPlaying()) preview.pause(); else preview.start();
    });

    details=label("รองรับไฟล์สูงสุด 3 GB • ความยาวแนะนำไม่เกิน 45 นาที",14,TEXT);
    root.addView(details);
    preview=new VideoView(this);
    root.addView(preview,new LinearLayout.LayoutParams(-1,dp(215)));
    preview.setMediaController(new MediaController(this));
    preview.setOnErrorListener((mp,what,extra)->{
      setStatus("เปิดภาพตัวอย่างไม่ได้ ("+what+") แต่ลองเพิ่มเวลาคิลด้วยตัวเลขได้");
      return true;
    });

    root.addView(label("1. ค้นหาคิลจากภาพแบนเนอร์และข้อความ",18,TEXT));
    root.addView(label("V5 นับจากจำนวนคิลส่วนตัวใน KDA ไม่ใช่แค่แถบมอนสเตอร์ • คิลติดกันนับแยก • ถ้า KDA อ่านไม่ได้ จะให้ตรวจแบนเนอร์ที่ยังไม่ยืนยัน",13,MUTED));
    LinearLayout scanRow=row(root);
    scanButton=button("AI ตรวจ KDA ฆ่าฮีโร่ V5",scanRow,v->scanForKills());
    cancelButton=button("ยกเลิกสแกน",scanRow,v->{stopScan.set(true);setStatus("กำลังยุติสแกน…");});
    cancelButton.setEnabled(false);

    root.addView(label("2. เพิ่มจังหวะคิลเอง / แก้ไขผล AI",18,TEXT));
    root.addView(label("ใช้ตัวควบคุมวิดีโอเลื่อนไปที่คิลแล้วกด เพิ่ม ณ ภาพ หรือใส่เวลาแบบ นาที:วินาที",13,MUTED));
    timeInput=new EditText(this);
    timeInput.setSingleLine(true);timeInput.setTextColor(TEXT);timeInput.setHintTextColor(MUTED);
    timeInput.setHint("เวลา 12:34 หรือ 12:34.5");
    timeInput.setInputType(InputType.TYPE_CLASS_TEXT);
    root.addView(timeInput,new LinearLayout.LayoutParams(-1,dp(52)));
    LinearLayout markRow=row(root);
    button("เพิ่มจากภาพ",markRow,v->addMark(preview.getCurrentPosition(),"เพิ่มเองจากวิดีโอ"));
    button("เพิ่มจากเวลา",markRow,v->addFromText());

    markerCount=label("รายการคิล: 0",17,TEXT);root.addView(markerCount);
    markList=new LinearLayout(this);markList.setOrientation(LinearLayout.VERTICAL);
    root.addView(markList);
    LinearLayout clearRow=row(root);
    button("ลบรายการทั้งหมด",clearRow,v->{if(!busy){marks.clear();renderMarks();}});
    button("เลือกทุกคิล",clearRow,v->{for(KillMark m:marks)m.enabled=true;renderMarks();});

    root.addView(label("3. เรนเดอร์ MP4 720p เน้นคุณภาพ",18,TEXT));
    root.addView(label("H.264 + เสียงเกม • ขอค่า bitrate 16 Mbps • รักษา FPS ต้นฉบับ (หากต้นฉบับ 60 FPS ผลลัพธ์จะเป็น 60 FPS)",13,MUTED));
    LinearLayout exportRow=row(root);
    exportButton=button("สร้างคลิปไฮไลท์",exportRow,v->export());
    progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
    progress.setMax(100);progress.setProgress(0);
    root.addView(progress,new LinearLayout.LayoutParams(-1,dp(14)));
    status=label("",14,TEXT);root.addView(status);
    root.addView(label("หมายเหตุ: V5 จำนวนคิลขึ้นกับวิดีโอจริง ไม่ตั้งค่า 9 หรือ 10 จุดตายตัว • การอ่าน KDA จาก HUD ยังเป็นรุ่นทดสอบ กรุณาตรวจจำนวนก่อนเรนเดอร์",13,MUTED));
  }

  private void setStatus(String s) { status.setText(s); }
  private void refreshButtons() {
    boolean loaded=videoUri != null;
    scanButton.setEnabled(loaded && !busy);
    exportButton.setEnabled(loaded && !busy && !marks.isEmpty());
    cancelButton.setEnabled(scanning);
  }

  private void chooseVideo() {
    if(busy) {setStatus("กำลังทำงานอยู่ กรุณายุติงานก่อนเปลี่ยนไฟล์");return;}
    Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT);
    pick.addCategory(Intent.CATEGORY_OPENABLE);
    pick.setType("video/*");pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
    startActivityForResult(pick,PICK_VIDEO);
  }

  @Override protected void onActivityResult(int requestCode,int resultCode,Intent data) {
    super.onActivityResult(requestCode,resultCode,data);
    if(requestCode != PICK_VIDEO || resultCode != RESULT_OK || data==null || data.getData()==null) return;
    Uri uri=data.getData();
    try {
      getContentResolver().takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION);
    } catch(Exception ignored) {}
    long size=-1;
    try(Cursor cursor=getContentResolver().query(uri,new String[]{OpenableColumns.SIZE},null,null,null)) {
      if(cursor!=null && cursor.moveToFirst()) size=cursor.getLong(0);
    } catch(Exception ignored){}
    if(size > MAX_BYTES) {setStatus("ไฟล์เกิน 3 GB กรุณาเลือกไฟล์เล็กกว่านี้");return;}
    MediaMetadataRetriever retriever=new MediaMetadataRetriever();
    try {
      retriever.setDataSource(this,uri);
      String val=retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
      long dur=val==null?0:Long.parseLong(val);
      if(dur<=0) throw new IllegalArgumentException("ไม่มีข้อมูลเวลาวิดีโอ");
      if(dur>45*60*1000L) {setStatus("คลิปนี้ยาวเกิน 45 นาที");return;}
      durationMs=dur; videoUri=uri; marks.clear();
      String fps="ไม่ทราบ";
      try {
        String rate=retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CAPTURE_FRAMERATE);
        if(rate!=null) fps=rate;
      } catch(Exception ignored){}
      details.setText("คลิป: "+HighlightPlanner.format(durationMs)+" • "+
          (size<0?"ไม่ทราบขนาด":String.format(Locale.US,"%.2f GB",size/1073741824.0))+
          " • FPS ต้นฉบับ: "+fps);
      preview.setVideoURI(uri);
      preview.seekTo(0);
      renderMarks();progress.setProgress(0);
      setStatus("นำเข้าวิดีโอสำเร็จ พร้อมสแกนคิล");
    } catch(Exception e) {setStatus("อ่านวิดีโอไม่ได้: "+e.getMessage());}
    finally {try {retriever.release();} catch(Exception ignored) {}}
    refreshButtons();
  }

  private void addFromText() {
    try {
      String s=timeInput.getText().toString().trim().replace(",",".");
      String[] p=s.split(":");
      if(p.length!=2) throw new IllegalArgumentException("รูปแบบต้องเป็น นาที:วินาที");
      long ms=(long)(Integer.parseInt(p[0])*60000L + Double.parseDouble(p[1])*1000.0);
      addMark(ms,"เพิ่มเองจากเวลา");
    } catch(Exception e) {setStatus("เวลาไม่ถูกต้อง: "+e.getMessage());}
  }

  private void addMark(long when,String reason) {
    if(videoUri == null || busy) return;
    if(when<0 || when>durationMs) {setStatus("เวลานอกช่วงวิดีโอ");return;}
    for(KillMark m:marks) if(Math.abs(m.when-when)<700) {setStatus("มีจังหวะคิลใกล้เวลานี้แล้ว");return;}
    marks.add(new KillMark(when,reason));renderMarks();
    setStatus("เพิ่มคิล "+HighlightPlanner.format(when)+" แล้ว");
  }

  private void renderMarks() {
    Collections.sort(marks,Comparator.comparingLong(m->m.when));
    markList.removeAllViews();
    long enabled=0;
    for(KillMark mark:marks) {
      if(mark.enabled)enabled++;
      LinearLayout r=row(markList);
      CheckBox cb=new CheckBox(this);
      cb.setButtonTintList(android.content.res.ColorStateList.valueOf(Color.rgb(86,190,244)));
      cb.setText(HighlightPlanner.format(mark.when)+"  "+mark.reason);
      cb.setTextColor(TEXT);cb.setTextSize(13);cb.setChecked(mark.enabled);
      cb.setOnCheckedChangeListener((v,on)->{mark.enabled=on;});
      r.addView(cb,new LinearLayout.LayoutParams(0,dp(48),1));
      Button seek=new Button(this);seek.setText("ดู");seek.setAllCaps(false);
      seek.setOnClickListener(v->{preview.seekTo((int)mark.when);preview.start();});
      r.addView(seek,new LinearLayout.LayoutParams(dp(55),dp(45)));
      Button del=new Button(this);del.setText("×");del.setAllCaps(false);
      del.setOnClickListener(v->{if(!busy){marks.remove(mark);renderMarks();}});
      r.addView(del,new LinearLayout.LayoutParams(dp(50),dp(45)));
    }
    markerCount.setText("รายการคิล: "+marks.size()+" • เลือก "+enabled+" จุด");
    refreshButtons();
  }

  /**
   * V2: sample 2.5 frames/sec to find visual HUD kill-strip cues,
   * then use OCR alongside visual recognition.
   * English can have stronger text evidence; Thai is *visual candidate only* because
   * bundled ML Kit Latin OCR does not support Thai script.
   */
  /** Read the personal K/D/A numerals from the in-game top HUD, not team score. */
  private KdaCounter.Observation readPersonalKda(Bitmap frame,TextRecognizer recognizer)
      throws Exception {
    int w=frame.getWidth(),h=frame.getHeight();
    int left=(int)(w*.40f);
    int cw=w-left;
    int ch=Math.max(1,(int)(h*.16f));
    Bitmap crop=null,upscaled=null;
    try {
      crop=Bitmap.createBitmap(frame,left,0,cw,ch);
      upscaled=Bitmap.createScaledBitmap(crop,cw*2,ch*2,true);
      Text ocr=Tasks.await(recognizer.process(InputImage.fromBitmap(upscaled,0)));
      List<KdaCounter.NumberBox> boxes=new ArrayList<>();
      for(Text.TextBlock block:ocr.getTextBlocks()){
        for(Text.Line line:block.getLines()){
          for(Text.Element element:line.getElements()){
            Rect bounds=element.getBoundingBox();
            if(bounds==null)continue;
            String number=element.getText().trim();
            if(number.matches("[0-9]{1,2}")){
              int n=Integer.parseInt(number);
              float x=(left + bounds.exactCenterX()*.5f)/w;
              float y=bounds.exactCenterY()*.5f/h;
              boxes.add(new KdaCounter.NumberBox(n,x,y));
            } else if(number.matches("[0-9]{1,2}[/\\\\-][0-9]{1,2}[/\\\\-][0-9]{1,2}")){
              // Some fonts OCR the full K/D/A string as one element.
              String[] fields=number.split("[/\\\\-]");
              float mid=(left + bounds.exactCenterX()*.5f)/w;
              float y=bounds.exactCenterY()*.5f/h;
              for(int i=0;i<3;i++)
                boxes.add(new KdaCounter.NumberBox(
                    Integer.parseInt(fields[i]),mid+(i-1)*.043f,y));
            }
          }
        }
      }
      return KdaCounter.parse(boxes);
    }finally{
      if(upscaled!=null)upscaled.recycle();
      if(crop!=null)crop.recycle();
    }
  }

  private void scanForKills() {
    if(busy || videoUri==null)return;
    stopScan.set(false);busy=true;scanning=true;refreshButtons();
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    progress.setProgress(0);
    setStatus("V5 ตรวจ KDA จำนวนคิลส่วนตัว + แบนเนอร์ประกาศคิล…");
    final Uri uri=videoUri;
    final long duration=durationMs;
    worker.execute(()->{
      MediaMetadataRetriever retriever=new MediaMetadataRetriever();
      TextRecognizer recognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
      KillVisionV2.Tracker bannerTracker=new KillVisionV2.Tracker();
      KdaCounter.Tracker personalKda=new KdaCounter.Tracker();
      List<KillMark> banners=new ArrayList<>();
      List<KdaCounter.Kill> kdaKills=new ArrayList<>();
      int frameErrors=0,ocrErrors=0,scanned=0;
      try {
        retriever.setDataSource(this,uri);
        final int step=KillVisionV2.SAMPLE_INTERVAL_MS;
        final long count=Math.max(1,(duration+step-1)/step);
        int[] pixels=null;
        long lastBannerOcrMs=-10000;
        for(long i=0;i<count && !stopScan.get();i++) {
          long atMs=Math.min(duration-1,i*step);
          Bitmap frame=null,bannerCrop=null;
          try {
            frame=retriever.getScaledFrameAtTime(atMs*1000L,
                MediaMetadataRetriever.OPTION_CLOSEST,960,540);
            if(frame==null){frameErrors++;continue;}
            int w=frame.getWidth(),h=frame.getHeight();
            if(pixels==null||pixels.length<w*h)pixels=new int[w*h];
            frame.getPixels(pixels,0,w,0,0,w,h);
            KillVisionV2.VisualSignal visual=KillVisionV2.analyze(pixels,w,h);
            if(i%3==0) {
              try {
                KdaCounter.Observation current=readPersonalKda(frame,recognizer);
                kdaKills.addAll(personalKda.feed(atMs,current));
              }catch(Exception e){ocrErrors++;}
            }
            KillVisionV2.TextSignal words=KillVisionV2.parseText("");
            boolean shouldBannerOcr=(visual.score>=.46||i%4==0) &&
                                     atMs-lastBannerOcrMs>=1150;
            if(shouldBannerOcr){
              lastBannerOcrMs=atMs;
              int x=(int)(w*.10),y=(int)(h*.052);
              int cw=Math.min(w-x,Math.max(1,(int)(w*.80)));
              int ch=Math.min(h-y,Math.max(1,(int)(h*.34)));
              bannerCrop=Bitmap.createBitmap(frame,x,y,cw,ch);
              try {
                String text=Tasks.await(recognizer.process(
                    InputImage.fromBitmap(bannerCrop,0))).getText();
                words=KillVisionV2.parseText(text);
              }catch(Exception e){ocrErrors++;}
            }
            KillVisionV2.Candidate visualMark=bannerTracker.feed(atMs,visual,words);
            if(visualMark!=null){
              boolean duplicate=false;
              for(KillMark old:banners)
                if(Math.abs(old.when-visualMark.timestampMs)<700L) {duplicate=true;break;}
              if(!duplicate)banners.add(new KillMark(visualMark.timestampMs,visualMark.reason));
            }
            scanned++;
          }catch(Exception e){frameErrors++;}
          finally{
            if(bannerCrop!=null)bannerCrop.recycle();
            if(frame!=null)frame.recycle();
          }
          if(i%6==0 || i==count-1){
            final int pct=(int)Math.min(100,100*(i+1)/count);
            final long seenMs=atMs;
            final int verified=kdaKills.size(),unverified=banners.size();
            main.post(()->{
              if(!scanning)return;
              progress.setProgress(pct);
              setStatus("สแกน "+pct+"% • "+HighlightPlanner.format(seenMs)+
                 " / "+HighlightPlanner.format(duration)+
                 " • KDA ยืนยัน "+verified+" คิล • แบนเนอร์ "+unverified+" จุด");
            });
          }
        }
        if(!stopScan.get()){
          KillVisionV2.Candidate tail=bannerTracker.finish(duration+1600L);
          if(tail!=null) banners.add(new KillMark(tail.timestampMs,tail.reason));
        }
        // KDA deltas are decisive. Use banner timestamps only to improve timing.
        // Never infer that a monster kill is a personal hero elimination.
        List<KillMark> output=new ArrayList<>();
        if(!kdaKills.isEmpty()){
          boolean[] used=new boolean[banners.size()];
          for(KdaCounter.Kill kill:kdaKills) {
            long when=kill.atMs;
            int nearest=-1;
            long gap=2600L;
            for(int j=0;j<banners.size();j++){
              if(used[j])continue;
              long distance=Math.abs(banners.get(j).when-when);
              if(distance<gap){nearest=j;gap=distance;}
            }
            if(nearest>=0){
              when=banners.get(nearest).when;
              used[nearest]=true;
            }
            KillMark m=new KillMark(when,"KDA ยืนยันคิลฮีโร่ของเรา #"+
                kill.individualTotal+(kill.inferred?" (คิลติดกัน)":""));
            output.add(m);
          }
        } else {
          // No reliable personal KDA: keep *proposed* video banner times visible,
          // but do not auto-select monsters or teammate kills as own kills.
          for(KillMark candidate:banners){
            candidate.enabled=false;
            candidate.reason="ยังไม่ยืนยัน (ต้องเช็กว่าเป็นคิลฮีโร่): "+candidate.reason;
            output.add(candidate);
          }
        }
        final int imagesFailed=frameErrors,ocrFailed=ocrErrors,framesDone=scanned;
        final int verified=kdaKills.size(),suggested=banners.size();
        final boolean calibrated=personalKda.isCalibrated();
        final boolean cancelled=stopScan.get();
        main.post(()->{
          // Preserve manually-added marks, replace previous automatic proposals.
          marks.removeIf(mark->mark.reason.startsWith("KDA ") ||
              mark.reason.startsWith("AI ") ||
              mark.reason.startsWith("ภาพแบนเนอร์") ||
              mark.reason.startsWith("ยังไม่ยืนยัน"));
          marks.addAll(output);
          scanning=false;busy=false;
          getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
          if(!cancelled)progress.setProgress(100);
          renderMarks();
          String summary;
          if(verified>0)
            summary="KDA ยืนยันจำนวนคิลฮีโร่ "+verified+
                " คิล • สร้าง "+verified+" ช็อต (คิลติดกันไม่ถูกควบรวม)";
          else if(calibrated)
            summary="อ่าน KDA ได้ แต่ยังไม่พบจำนวนคิลส่วนตัวเพิ่ม • มีแบนเนอร์ที่ไม่ยืนยัน "+suggested+" จุด";
          else
            summary="ยังอ่านตำแหน่ง KDA ส่วนตัวไม่สำเร็จ • พบแบนเนอร์ "+suggested+
                " จุด ซึ่งยกเลิกเลือกไว้เพื่อป้องกันตัดมอนสเตอร์ผิด";
          if(framesDone==0)summary="ไม่สามารถถอดภาพคลิปได้ ตรวจสอบไฟล์ MP4 ที่เปิดได้";
          if(imagesFailed>0||ocrFailed>0)
            summary+=" • ภาพเสีย "+imagesFailed+" / OCR ผิดพลาด "+ocrFailed;
          setStatus((cancelled?"ยกเลิกสแกน • ":"สแกนเสร็จ • ")+summary);
        });
      }catch(Exception error){
        main.post(()->{
          scanning=false;busy=false;
          getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
          refreshButtons();
          setStatus("สแกนผิดพลาด: "+error.getMessage());
        });
      }finally{
        try{retriever.release();}catch(Exception ignored){}
        recognizer.close();
      }
    });
  }

  private void export() {
    if(busy || videoUri==null)return;
    List<Long> selected=new ArrayList<>();
    for(KillMark mark:marks) if(mark.enabled)selected.add(mark.when);
    List<HighlightPlanner.Range> ranges=HighlightPlanner.calculate(selected,durationMs);
    if(ranges.isEmpty()) {setStatus("ยังไม่มีคิลที่เลือก");return;}
    File dir=getExternalFilesDir(Environment.DIRECTORY_MOVIES);
    if(dir==null){setStatus("เปิดพื้นที่จัดเก็บไฟล์ไม่ได้");return;}
    if(!dir.exists()&&!dir.mkdirs()){setStatus("สร้างโฟลเดอร์ส่งออกไม่ได้");return;}
    long totalMs=0;
    for(HighlightPlanner.Range r:ranges) totalMs += r.endMs-r.startMs;
    long approxBytes=(long)(totalMs/1000.0 * (16_000_000.0+256_000.0)/8.0 * 1.4);
    StatFs stat=new StatFs(dir.getAbsolutePath());
    if(stat.getAvailableBytes()<approxBytes+100L*1024*1024){
      setStatus("พื้นที่ว่างไม่พอ แนะนำเคลียร์พื้นที่ก่อนเรนเดอร์");return;
    }
    outputFile=new File(dir,"hok_highlight_"+System.currentTimeMillis()+".mp4");
    busy=true;refreshButtons();progress.setProgress(0);
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    setStatus("เริ่มเรนเดอร์ "+ranges.size()+" ช่วง • ประมาณ "+HighlightPlanner.format(totalMs)+"…");
    try {
      List<EditedMediaItem> clips=new ArrayList<>();
      for(HighlightPlanner.Range r:ranges){
        MediaItem src=new MediaItem.Builder()
            .setUri(videoUri)
            .setClippingConfiguration(new MediaItem.ClippingConfiguration.Builder()
              .setStartPositionMs(r.startMs).setEndPositionMs(r.endMs).build())
            .build();
        clips.add(new EditedMediaItem.Builder(src).build());
      }
      EditedMediaItemSequence sequence=EditedMediaItemSequence.withAudioAndVideoFrom(clips);
      Composition composition=new Composition.Builder(sequence)
          .setEffects(new Effects(Collections.emptyList(),
             Collections.singletonList(Presentation.createForHeight(720))))
          .build();
      DefaultEncoderFactory encoder=new DefaultEncoderFactory.Builder(this)
          .setRequestedVideoEncoderSettings(new VideoEncoderSettings.Builder()
              .setBitrate(16_000_000).setiFrameIntervalSeconds(2f).build())
          .setEnableFallback(true).build();
      transformer=new Transformer.Builder(this)
          .setVideoMimeType(MimeTypes.VIDEO_H264)
          .setAudioMimeType(MimeTypes.AUDIO_AAC)
          .setEncoderFactory(encoder)
          .addListener(new Transformer.Listener(){
            @Override public void onCompleted(Composition composition,ExportResult result){
              setStatus("เรนเดอร์เสร็จ กำลังบันทึกลงแกลเลอรี…");
              File saved=outputFile;
              worker.execute(()->{
                try {String dest=saveToGallery(saved);
                  main.post(()->{finishExport();progress.setProgress(100);
                    setStatus("บันทึกสำเร็จใน Movies/HOK Highlights\n"+dest);});
                }catch(Exception e){
                  main.post(()->{finishExport();setStatus("เรนเดอร์สำเร็จ แต่ย้ายเข้าแกลเลอรีไม่สำเร็จ: "+e.getMessage()+
                    "\nต้นฉบับผลลัพธ์อยู่ในพื้นที่แอป: "+saved.getAbsolutePath());});
                }
              });
            }
            @Override public void onError(Composition composition,ExportResult result,ExportException error){
              finishExport();setStatus("เรนเดอร์ไม่สำเร็จ: "+error.getMessage());
            }
          }).build();
      transformer.start(composition,outputFile.getAbsolutePath());
      pollExportProgress();
    }catch(Exception e){finishExport();setStatus("เริ่มเรนเดอร์ไม่สำเร็จ: "+e.getMessage());}
  }

  private void pollExportProgress(){
    if(!busy || transformer==null) return;
    ProgressHolder holder=new ProgressHolder();
    try {
      int state=transformer.getProgress(holder);
      if(state==Transformer.PROGRESS_STATE_AVAILABLE) {
        progress.setProgress(holder.progress);
        setStatus("กำลังเรนเดอร์ไฮไลท์ • "+holder.progress+"% • อย่าปิดแอป");
      }
    } catch(Exception ignored){}
    main.postDelayed(()->{if(busy && transformer!=null)pollExportProgress();},850);
  }

  private String saveToGallery(File source) throws Exception {
    ContentResolver resolver=getContentResolver();
    ContentValues values=new ContentValues();
    values.put(MediaStore.Video.Media.DISPLAY_NAME,source.getName());
    values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");
    values.put(MediaStore.Video.Media.RELATIVE_PATH,Environment.DIRECTORY_MOVIES+"/HOK Highlights");
    values.put(MediaStore.Video.Media.IS_PENDING,1);
    Uri dest=resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);
    if(dest==null)throw new IllegalStateException("สร้างไฟล์ในแกลเลอรีไม่ได้");
    try {
      try(InputStream input=new FileInputStream(source);OutputStream output=resolver.openOutputStream(dest)){
        if(output==null)throw new IllegalStateException("เขียนปลายทางไม่ได้");
        byte[] buffer=new byte[1024*1024];int n;
        while((n=input.read(buffer))!=-1)output.write(buffer,0,n);
      }
      ContentValues done=new ContentValues();done.put(MediaStore.Video.Media.IS_PENDING,0);
      resolver.update(dest,done,null,null);
      source.delete();
      return source.getName();
    }catch(Exception e){resolver.delete(dest,null,null);throw e;}
  }

  private void finishExport(){
    busy=false;scanning=false;transformer=null;
    getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    refreshButtons();
  }

  @Override protected void onDestroy(){
    stopScan.set(true);
    if(transformer!=null){try{transformer.cancel();}catch(Exception ignored){}}
    worker.shutdownNow();
    super.onDestroy();
  }
}
