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
   * Sole source of an automatic hero-kill event: a CONFIRMED INCREASE in
   * the player's personal sword/K counter after stable HUD calibration.
   * Do not use a banner, portrait, monster, teammate, objective or death
   * event to create, approve, reject or retime the cut.
   * Example sword 0 -> sword 1, later 1 -> 2 = exactly two cuts.
   */
  public static List<Decision> reconcile(List<KdaCounter.Kill> kda,
      List<Banner> banners,List<Long> ownDeaths) {
    List<Decision> out=new ArrayList<>();
    if(kda==null)return out;
    for(KdaCounter.Kill kill:kda) {
      if(kill==null)continue;
      boolean selected=kill.trustedHud;
      String reason=selected
          ? "เลขดาบ K ของเราเพิ่มเป็น "+kill.individualTotal
          : "เลขดาบ K ยังอ่านไม่แน่ชัด • ต้องตรวจเอง";
      if(kill.inferred)reason+=" • K เพิ่มหลายครั้งระหว่างสองภาพ";
      out.add(new Decision(kill.atMs,reason,selected,true));
    }
    out.sort((a,b)->Long.compare(a.atMs,b.atMs));
    return out;
  }
}
