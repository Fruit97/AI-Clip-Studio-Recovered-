package com.pad6.hokhighlight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * Combines the PERSONAL K counter with enemy-hero kill announcements.
 * Monster/objective/death UI graphics are NOT positive kill evidence.
 * This is a conservative on-device heuristic, not a trained game-event model.
 */
public final class KillReconcilerV7 {
  private KillReconcilerV7() {}
  public static final class Banner {
    public final long atMs;
    public final String reason;
    public Banner(long at,String reason) { atMs=at;this.reason=reason==null?"":reason; }
    public boolean objectiveText() {
      String t=reason.toLowerCase(Locale.ROOT);
      return t.contains("objective:") || HeroOnlyGuard.objectiveWord(t)!=null;
    }
    public boolean heroicText() {
      String t=reason.toLowerCase(Locale.ROOT);
      // Neutral objectives can say "slain", "defeated", even "you have slain".
      if(HeroOnlyGuard.objectiveWord(t)!=null ||
         t.contains("objective:") ||
         t.contains("you have been slain") ||
         t.contains("you have been defeated"))return false;
      // Enemy and ally streak notifications are not personal kills.
      String[] otherPlayer={"enemy double kill","enemy doublekill",
         "enemy triple kill","enemy triplekill","enemy quadra kill",
         "enemy quadrakill","enemy penta kill","enemy pentakill",
         "enemy godlike","enemy legendary","enemy first blood",
         "ally double kill","ally triple kill","ally quadra kill",
         "ally penta kill","ally first blood","teammate double kill",
         "teammate triple kill","an ally has slain",
         "an enemy has slain","opponent double kill",
         "ฝ่ายตรงข้ามดับเบิลคิล","ฝ่ายตรงข้ามทริปเปิลคิล"};
      for(String phrase:otherPlayer)if(t.contains(phrase))return false;
      // These banners are specific to HERO-versus-HERO eliminations.
      // A generic Double/Triple/Penta Kill can refer to any teammate/enemy.
      // Never treat it as independently verified OWN hero-kill evidence.
      String[] labels={"you have slain an enemy hero", "you have defeated an enemy hero",
         "you have killed an enemy hero", "you have slain an enemy",
         "you have defeated an enemy", "you killed an enemy",
         "คุณสังหารฮีโร่ศัตรู", "คุณกำจัดฮีโร่ศัตรู"};
      for(String value:labels)if(t.contains(value))return true;
      return false;
    }
  }
  public static final class Decision {
    public final long atMs;
    public final String reason;
    public final boolean selected;
    public final boolean fromCounter;
    Decision(long time,String note,boolean selected,boolean fromCounter) {
      atMs=time;reason=note;this.selected=selected;this.fromCounter=fromCounter;
    }
  }

  public static boolean nearDeath(long time,List<Long> deathTimes) {
    if(deathTimes==null)return false;
    for(Long d:deathTimes)if(d!=null && Math.abs(time-d)<=2100L)return true;
    return false;
  }

  /**
   * One K-counter increase -> one candidate, even when two kills occur within
   * a single second. Auto-select only strong HUD or weak KDA + independent,
   * hero-specific text evidence. Deaths and generic banners do NOT auto-select.
   */
  public static List<Decision> reconcile(List<KdaCounter.Kill> kda,
      List<Banner> banners,List<Long> ownDeaths) {
    List<KdaCounter.Kill> kills=kda==null?Collections.emptyList():kda;
    List<Banner> notices=banners==null?Collections.emptyList():banners;
    boolean[] used=new boolean[notices.size()];
    List<Decision> out=new ArrayList<>();
    for(KdaCounter.Kill kill:kills) {
      int nearest=-1;long gap=2600L;
      for(int j=0;j<notices.size();j++) {
        Banner b=notices.get(j);
        if(used[j]||!b.heroicText())continue;
        long delta=Math.abs(kill.atMs-b.atMs);
        if(delta<gap) {gap=delta;nearest=j;}
      }
      if(nearest>=0) used[nearest]=true;
      boolean atDeath=nearDeath(kill.atMs,ownDeaths);
      boolean corroborated=nearest>=0;
      // Objective OCR contradicts a possible kill at the same instant.
      // Leave simultaneous events for manual review: precision over recall.
      boolean objectiveConflict=false;
      for(Banner b:notices)
        if(b.objectiveText() && Math.abs(kill.atMs-b.atMs)<=1800L) {
          objectiveConflict=true; break;
        }
      // Personal K rises shortly before death remain valid;
      // simultaneous K+D changes are already rejected by the tracker.
      boolean selected=!objectiveConflict &&
          (kill.trustedHud || (corroborated && !atDeath));
      long time=corroborated?notices.get(nearest).atMs:kill.atMs;
      String reason;
      if(objectiveConflict)
        reason="Objective ใกล้คิล (ตรวจเอง ไม่เลือกตัดอัตโนมัติ)";
      else if(kill.trustedHud) reason="K/D/A ส่วนตัวยืนยันค่า K เพิ่ม #"+kill.individualTotal+
          (atDeath?" • คิลก่อนตาย (ตัดปลายก่อนหน้าจอตาย)":"");
      else if(atDeath) reason="ค่า K ยังไม่ยืนยันและใกล้เวลาตาย (ไม่เลือก)";
      else if(corroborated) reason="K เพิ่ม + พบข้อความคิลฮีโร่ #"+kill.individualTotal;
      else reason="ค่า K เพิ่ม แต่ตัวเลข K/D/A ยังไม่ยืนยัน (ไม่เลือก)";
      if(kill.inferred)reason+=" • คิลติดกัน";
      out.add(new Decision(time,reason,selected,true));
    }
    for(int j=0;j<notices.size();j++) {
      if(used[j])continue;
      Banner b=notices.get(j);
      if(b.objectiveText() || nearDeath(b.atMs,ownDeaths))continue;
      boolean covered=false;
      for(Decision x:out) if(Math.abs(x.atMs-b.atMs)<1100L) {covered=true;break;}
      if(!covered) out.add(new Decision(b.atMs,
          "แบนเนอร์ยังไม่ยืนยันว่าเป็นคิลของเรา (ไม่เลือก): "+b.reason,false,false));
    }
    out.sort((a,b)->Long.compare(a.atMs,b.atMs));
    return out;
  }
}
