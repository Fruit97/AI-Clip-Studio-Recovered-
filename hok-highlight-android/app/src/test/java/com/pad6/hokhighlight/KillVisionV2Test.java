package com.pad6.hokhighlight;

import org.junit.Test;
import static org.junit.Assert.*;

public class KillVisionV2Test {
  @Test public void ownKillAndDeathAreSeparated() {
    assertEquals(KillVisionV2.Category.OWN,
      KillVisionV2.parseText("You have defeated an enemy!").category);
    assertEquals(KillVisionV2.Category.OTHER,
      KillVisionV2.parseText("You have been defeated").category);
    assertEquals(KillVisionV2.Category.OTHER,
      KillVisionV2.parseText("Enemy Double Kill").category);
    assertEquals(KillVisionV2.Category.MAYBE,
      KillVisionV2.parseText("QUADRAKILL!").category);
    assertEquals(KillVisionV2.Category.MAYBE,
      KillVisionV2.parseText("Godlike!").category);
    assertEquals(KillVisionV2.Category.MAYBE,
      KillVisionV2.parseText("DEFEAT!").category);
    assertEquals(KillVisionV2.Category.NONE,
      KillVisionV2.parseText("Tap your skills").category);
    assertEquals(KillVisionV2.Category.NONE,
      KillVisionV2.parseText("Retreat! Attack the tower").category);
  }
  @Test public void ownThaiPhraseSupportedIfTextWasDecoded() {
    assertEquals(KillVisionV2.Category.OWN,
      KillVisionV2.parseText("คุณสังหารศัตรู").category);
    assertEquals(KillVisionV2.Category.OTHER,
      KillVisionV2.parseText("คุณถูกสังหาร").category);
  }
  @Test public void highContrastBannerVsOrdinaryAndLoadingFrames() {
    int w=640,h=360;
    int[] plain = new int[w*h];
    int[] black = new int[w*h];
    int[] banner = new int[w*h];
    java.util.Arrays.fill(plain,0xff668843);
    java.util.Arrays.fill(black,0xff080808);
    System.arraycopy(plain,0,banner,0,plain.length);
    rect(banner,w,h,.35,.65,.155,.217,0xff101823);
    rect(banner,w,h,.205,.315,.13,.235,0xff185ed8);
    rect(banner,w,h,.685,.795,.13,.235,0xffcc2635);
    double blank=KillVisionV2.analyze(plain,w,h).score;
    double dark=KillVisionV2.analyze(black,w,h).score;
    double hero=KillVisionV2.analyze(banner,w,h).score;
    assertTrue("banner: "+hero+", plain: "+blank,hero>blank+.2);
    assertTrue("banner above threshold",hero>.61);
    assertTrue("loading screen not banner",dark<.61);
  }
  private static void rect(int[] pixels,int w,int h,double x0,double x1,double y0,double y1,int c){
    for(int y=(int)(y0*h);y<(int)(y1*h);y++)
      for(int x=(int)(x0*w);x<(int)(x1*w);x++)
        pixels[y*w+x]=c;
  }
  @Test public void rejectsNeutralMonsterTextEvenIfSlain() {
    String[] neutral = {
      "You have slain the Tyrant!", "You have slain the Shadow Overlord",
      "The Tempest Dragon was slain", "You defeated a jungle monster",
      "Your team defeated the blue buff", "Dragon Vanguard incoming",
      "คุณสังหารมังกรพายุ", "คุณสังหารมอนสเตอร์", "ฆ่าครีป"
    };
    for(String n:neutral)assertEquals(n,KillVisionV2.Category.OTHER,KillVisionV2.parseText(n).category);
    assertEquals(KillVisionV2.Category.OWN,
      KillVisionV2.parseText("You have slain an enemy hero").category);
  }

  @Test public void singleIconBossBannerMustNotLookLikeTwoHeroPortraits() {
    int w=640,h=360;int[] boss=new int[w*h];java.util.Arrays.fill(boss,0xff668843);
    rect(boss,w,h,.35,.65,.155,.217,0xff101823);
    rect(boss,w,h,.205,.315,.13,.235,0xff185ed8);
    KillVisionV2.VisualSignal result=KillVisionV2.analyze(boss,w,h);
    assertFalse("single boss icon falsely matched hero portraits",
      HeroOnlyGuard.isHeroPortraitPair(result));
  }

  @Test public void trackerEmitsOneEventPerPersistentBannerAfterVetoWindow(){
    KillVisionV2.Tracker tracker=new KillVisionV2.Tracker();
    KillVisionV2.VisualSignal cue=new KillVisionV2.VisualSignal(.85,.92,.7,.7);
    KillVisionV2.TextSignal none=KillVisionV2.parseText("");
    assertNull(tracker.feed(1000,cue,none));
    assertNull(tracker.feed(1400,cue,none)); // provisional, wait to exclude monsters
    assertNull(tracker.feed(1900,cue,none));
    assertNotNull(tracker.feed(2600,cue,none));
    assertNull(tracker.feed(4000,cue,none));
    KillVisionV2.VisualSignal ordinary=new KillVisionV2.VisualSignal(.12,.2,.3,.1);
    tracker.feed(4400,ordinary,none);
    tracker.feed(4800,ordinary,none);
    assertNull(tracker.feed(5200,cue,none));
    assertNull(tracker.feed(5600,cue,none));
    assertNotNull(tracker.feed(6800,cue,none));
  }

  @Test public void objectiveTextCancelsPendingVisualEvent(){
    KillVisionV2.Tracker tracker=new KillVisionV2.Tracker();
    KillVisionV2.VisualSignal cue=new KillVisionV2.VisualSignal(.88,.92,.8,.8);
    KillVisionV2.TextSignal none=KillVisionV2.parseText("");
    tracker.feed(1000,cue,none);
    assertNull(tracker.feed(1400,cue,none));
    assertNull(tracker.feed(1800,cue,KillVisionV2.parseText("Team defeated Tyrant")));
    assertNull(tracker.feed(2600,cue,none));
    assertNull(tracker.finish(4000));
  }

  @Test public void ownOcrCanDetectWithoutVisualBannerAfterVetoWindow(){
    KillVisionV2.Tracker tracker=new KillVisionV2.Tracker();
    KillVisionV2.VisualSignal poor=new KillVisionV2.VisualSignal(.1,.3,.2,.2);
    assertNull(tracker.feed(3000,poor,KillVisionV2.parseText("You have slain an enemy")));
    assertNotNull(tracker.feed(4200,poor,KillVisionV2.parseText("")));
  }
}
