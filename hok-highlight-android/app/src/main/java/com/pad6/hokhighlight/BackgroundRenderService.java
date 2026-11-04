package com.pad6.hokhighlight;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Foreground status/notification companion for the existing V8.3 processing.
 *
 * This class does NOT change hero-kill detection, OCR, timestamps or MP4
 * rendering. A foreground service keeps the application process prioritized
 * while the Activity's existing job runs after switching apps/screen off.
 *
 * It does not restart a partially completed process after force-stop/reboot.
 */
public final class BackgroundRenderService extends Service {
  private static final String CHANNEL_WORK="hok_highlight_work_v1";
  private static final String CHANNEL_DONE="hok_highlight_done_v1";
  private static final int WORK_NOTIFICATION=5101;
  private static final int DONE_NOTIFICATION=5102;
  private static final String ACTION_BEGIN="com.pad6.hokhighlight.BEGIN";
  private static volatile BackgroundRenderService active;
  private static volatile boolean requested;
  private static volatile String currentStage="กำลังเตรียมงาน";
  private static volatile int currentPercent;
  private PowerManager.WakeLock cpuLock;
  private boolean foreground;
  private int shownPercent=-1;
  private String shownStage="";
  private NotificationManager notifications;

  public static boolean isRunning(){return requested;}
  public static String status(){
    return currentStage+" • "+currentPercent+"%";
  }

  /** Must be invoked while the app is visible, before submitting a job. */
  public static boolean begin(Context context,String stage) {
    if(requested) {
      progress(context,stage,0);
      return true;
    }
    currentStage=stage;
    currentPercent=0;
    requested=true;
    try {
      Intent intent=new Intent(context,BackgroundRenderService.class);
      intent.setAction(ACTION_BEGIN);
      context.startForegroundService(intent);
      return true;
    }catch(Exception e){
      requested=false;
      android.util.Log.e("HOKBackground","Cannot start foreground service",e);
      return false;
    }
  }

  /** Lightweight progress update; does not repeatedly restart a service. */
  public static void progress(Context context,String stage,int percent) {
    if(!requested)return;
    currentStage=stage==null?"กำลังประมวลผล":stage;
    currentPercent=Math.max(0,Math.min(100,percent));
    BackgroundRenderService service=active;
    if(service!=null)service.postProgress();
  }

  /** End foreground CPU work and post a separate completion notification. */
  public static void finish(Context context,boolean success,String message) {
    if(!requested)return;
    requested=false;
    BackgroundRenderService service=active;
    if(service!=null)service.postFinish(success,message);
    else {
      // Rare case: a very short job finishes before onStartCommand.
      // onStartCommand reads requested=false and posts the terminal update.
      terminalSuccess=success;
      terminalMessage=message;
    }
  }
  private static volatile Boolean terminalSuccess;
  private static volatile String terminalMessage;

  @Override public void onCreate(){
    super.onCreate();
    notifications=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
    NotificationChannel running=new NotificationChannel(
        CHANNEL_WORK,"ประมวลผลไฮไลท์ HOK",NotificationManager.IMPORTANCE_LOW);
    running.setDescription("แสดงสถานะการสแกนและเรนเดอร์วิดีโอขณะใช้แอปอื่น");
    NotificationChannel completed=new NotificationChannel(
        CHANNEL_DONE,"ผลการสร้างไฮไลท์ HOK",NotificationManager.IMPORTANCE_DEFAULT);
    completed.setDescription("แจ้งเมื่อสร้างวิดีโอเสร็จหรือเกิดข้อผิดพลาด");
    notifications.createNotificationChannel(running);
    notifications.createNotificationChannel(completed);
  }

  @Override public int onStartCommand(Intent intent,int flags,int startId){
    if(intent==null || !ACTION_BEGIN.equals(intent.getAction())){
      stopSelf();
      return START_NOT_STICKY;
    }
    active=this;
    try{
      Notification notification=buildRunning(currentStage,currentPercent);
      if(Build.VERSION.SDK_INT>=34)
        startForeground(WORK_NOTIFICATION,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
      else
        startForeground(WORK_NOTIFICATION,notification);
      foreground=true;
      PowerManager power=(PowerManager)getSystemService(POWER_SERVICE);
      cpuLock=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"HOKHighlight:Work");
      cpuLock.setReferenceCounted(false);
      // Bounded failsafe; normal completion/cancellation releases it sooner.
      cpuLock.acquire(3L*60L*60L*1000L);
      if(!requested) {
        Boolean done=terminalSuccess;
        String text=terminalMessage;
        terminalSuccess=null;terminalMessage=null;
        postFinish(done!=null&&done,text==null?"ประมวลผลเสร็จแล้ว":text);
      }
    }catch(Exception e){
      android.util.Log.e("HOKBackground","Foreground notification failed",e);
      requested=false;
      stopSelf();
    }
    return START_NOT_STICKY;
  }

  private PendingIntent openApp(){
    Intent intent=new Intent(this,MainActivity.class);
    intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
    return PendingIntent.getActivity(this,0,intent,
        PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
  }

  private Notification buildRunning(String stage,int percent){
    return new Notification.Builder(this,CHANNEL_WORK)
        .setSmallIcon(android.R.drawable.ic_media_play)
        .setContentTitle("HOK Highlight AI • กำลังประมวลผล")
        .setContentText(stage+" • "+percent+"%")
        .setContentIntent(openApp())
        .setProgress(100,percent,false)
        .setCategory(Notification.CATEGORY_PROGRESS)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setShowWhen(false)
        .build();
  }

  private void postProgress(){
    new android.os.Handler(getMainLooper()).post(()->{
      if(!foreground || !requested)return;
      String stage=currentStage;
      int percent=currentPercent;
      if(shownPercent==percent && stage.equals(shownStage))return;
      shownPercent=percent;
      shownStage=stage;
      notifications.notify(WORK_NOTIFICATION,buildRunning(stage,percent));
    });
  }

  private void postFinish(boolean success,String message){
    new android.os.Handler(getMainLooper()).post(()->{
      String detail=(message==null || message.trim().isEmpty())
          ? (success?"สร้างไฮไลท์ MP4 สำเร็จ":"งานประมวลผลสิ้นสุด")
          :message;
      Notification done=new Notification.Builder(this,CHANNEL_DONE)
          .setSmallIcon(android.R.drawable.ic_media_play)
          .setContentTitle(success?"สร้างไฮไลท์ HOK เสร็จแล้ว":"สถานะงาน HOK Highlight AI")
          .setContentText(detail)
          .setStyle(new Notification.BigTextStyle().bigText(detail))
          .setContentIntent(openApp())
          .setCategory(Notification.CATEGORY_STATUS)
          .setAutoCancel(true)
          .setShowWhen(true)
          .build();
      if(foreground){
        stopForeground(STOP_FOREGROUND_REMOVE);
        foreground=false;
      }
      notifications.notify(DONE_NOTIFICATION,done);
      stopSelf();
    });
  }

  @Override public void onDestroy(){
    if(cpuLock!=null && cpuLock.isHeld())cpuLock.release();
    cpuLock=null;
    if(active==this)active=null;
    // If killed during a job, the foreground service cannot promise resume.
    requested=false;
    super.onDestroy();
  }

  @Override public IBinder onBind(Intent intent){return null;}
}
