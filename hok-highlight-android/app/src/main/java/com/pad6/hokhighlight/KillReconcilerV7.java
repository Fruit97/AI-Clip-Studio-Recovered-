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
    public boolean heroicText() {
      String t=reason.toLowerCase(Locale.ROOT);
      // Neutral objectives can say "slain", "defeated", even "you have slain".
      if(HeroOnlyGuard.objectiveWord(t)!=null ||
         t.contains("objective:") || t.contains("enemy double kill") ||
         t.contains("you have been slain") ||
         t.contains("you have been defeated"))return false;
      // These banners are specific to HERO-versus-HERO eliminations.
      String[] labels={"you have slain an enemy hero", "you have defeated an enemy hero",
         "you have slain an enemy", "you have defeated an enemy",
         "double kill", "doublekill", "triple kill", "triplekill",
         "quadra kill", "quadrakill", "penta kill", "pentakill",
         "legendary", "godlike", "first blood", "mega kill",
         "ดับเบิลคิล", "ทริปเปิลคิล", "ฆ่าสอง", "ฆ่าสาม", "ฆ่าสี่", "ฆ่าห้า"};
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
      boolean selected=!atDeath && (kill.trustedHud || corroborated);
      long time=(corroborated && !atDeath)?notices.get(nearest).atMs:kill.atMs;
      String reason;
      if(atDeath) reason="คิลใกล้การตายของเรา (ไม่เลือกตัด)";
      else if(kill.trustedHud) reason="K/D/A ส่วนตัวยืนยันค่า K เพิ่ม #"+kill.individualTotal;
      else if(corroborated) reason="K เพิ่ม + พบข้อความคิลฮีโร่ #"+kill.individualTotal;
      else reason="ค่า K เพิ่ม แต่ตัวเลข K/D/A ยังไม่ยืนยัน (ไม่เลือก)";
      if(kill.inferred)reason+=" • คิลติดกัน";
      out.add(new Decision(time,reason,selected,true));
    }
    for(int j=0;j<notices.size();j++) {
      if(used[j])continue;
      Banner b=notices.get(j);
      if(nearDeath(b.atMs,ownDeaths))continue;
      boolean covered=false;
      for(Decision x:out) if(Math.abs(x.atMs-b.atMs)<1100L) {covered=true;break;}
      if(!covered) out.add(new Decision(b.atMs,
          "แบนเนอร์ยังไม่ยืนยันว่าเป็นคิลของเรา (ไม่เลือก): "+b.reason,false,false));
    }
    out.sort((a,b)->Long.compare(a.atMs,b.atMs));
    return out;
  }
}
