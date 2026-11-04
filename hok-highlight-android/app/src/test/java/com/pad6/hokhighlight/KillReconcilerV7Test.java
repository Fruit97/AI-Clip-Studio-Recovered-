package com.pad6.hokhighlight;
import org.junit.Test;
import java.util.*;
import static org.junit.Assert.*;

public class KillReconcilerV7Test {
  private KillReconcilerV7.Banner b(long at,String text){
    return new KillReconcilerV7.Banner(at,text);
  }
  private KdaCounter.Kill k(long at,int count,boolean hud){
    return new KdaCounter.Kill(at,count,false,hud);
  }
  private long selected(List<KillReconcilerV7.Decision> picks){
    return picks.stream().filter(x->x.selected).count();
  }

  @Test public void monsterBannerNeverCreatesAutoHighlight() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Collections.emptyList(),
      Arrays.asList(b(5000,"ภาพแบนเนอร์มอนสเตอร์"),
                    b(10000,"OCR พบคิล: You have slain the Tyrant"),
                    b(15000,"Overlord defeated")),
      Collections.emptyList());
    assertEquals(0,selected(d));
  }
  @Test public void personalKillJustBeforeDeathIsKeptAndTailTrimmed() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(9000,3,true)),
      Arrays.asList(b(9200,"OCR พบคิล: You have slain an enemy hero")),
      Arrays.asList(11800L));
    assertEquals(1,selected(d));
    List<HighlightPlanner.Range> shots=HighlightPlanner.calculateAvoidDeaths(
        Arrays.asList(d.get(0).atMs),Arrays.asList(11800L),20000L);
    assertEquals(1,shots.size());assertEquals(11000L,shots.get(0).endMs);
  }
  @Test public void weakKdaNearDeathIsNotSelected() {
    assertEquals(0,selected(KillReconcilerV7.reconcile(
      Arrays.asList(k(9000,3,false)),
      Arrays.asList(b(9200,"OCR พบคิล: You have slain an enemy hero")),
      Arrays.asList(9800L))));
  }
  @Test public void enemyAndAllyStreaksDoNotVerifyWeakKda() {
    for(String name:Arrays.asList("Enemy Triple Kill","Enemy Penta Kill",
        "Ally Double Kill","Enemy Godlike","Ally First Blood")) {
      assertFalse(name,b(0,"OCR: "+name).heroicText());
      assertEquals(0,selected(KillReconcilerV7.reconcile(
          Arrays.asList(k(10000,3,false)),
          Arrays.asList(b(10200,"OCR: "+name)),Collections.emptyList())));
    }
    assertFalse(b(0,"First Blood").heroicText());
  }
  @Test public void strongPersonalKdaKillIsSelectedWithoutBanner() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(9000,4,true)),Collections.emptyList(),Collections.emptyList());
    assertEquals(1,selected(d));assertEquals(9000,d.get(0).atMs);
  }
  @Test public void untrustedTeamScoreCannotTriggerMonsterHighlight() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(7000,4,false)),
      Arrays.asList(b(7200,"ภาพแบนเนอร์ V2"),b(22000,"OCR: monster slain")),
      Collections.emptyList());
    assertEquals(0,selected(d));
  }
  @Test public void weakKdaCannotBeSelectedByBanner() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,2,false)),
      Arrays.asList(b(10200,"ข้อความประกาศคิล: you have slain an enemy hero")),
      Collections.emptyList());
    assertEquals(0,selected(d));
    assertEquals(10000,d.get(0).atMs);
  }
  @Test public void genericMultikillDoesNotVerifyPersonalKill() {
    for(String notice:Arrays.asList("double kill","triple kill","penta kill",
        "ดับเบิลคิล","ทริปเปิลคิล")) {
      assertEquals(notice,0,selected(KillReconcilerV7.reconcile(
        Arrays.asList(k(10000,2,false)),
        Arrays.asList(b(10200,"ประกาศ: "+notice)),Collections.emptyList())));
    }
  }
  @Test public void objectiveCannotCancelVerifiedPersonalKIncrement() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,3,true)),
      Arrays.asList(b(10500,"objective:tyrant")),Collections.emptyList());
    assertEquals(1,selected(d));
    assertEquals(10000L,d.get(0).atMs);
  }
  @Test public void distantObjectiveDoesNotVetoOwnHeroKill() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,3,true)),
      Arrays.asList(b(4500,"objective:overlord")),Collections.emptyList());
    assertEquals(1,selected(d)); assertEquals(1,d.size());
  }
  @Test public void objectiveOnlyIsNotEvenSuggestedAsHighlight() {
    assertTrue(KillReconcilerV7.reconcile(Collections.emptyList(),
        Arrays.asList(b(10000,"objective:tyrant")),Collections.emptyList()).isEmpty());
  }
  @Test public void weakKdaPlusGenericDefeatCannotAutoSelect() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,2,false)),
      Arrays.asList(b(10200,"ข้อความประกาศคิล: defeat")),
      Collections.emptyList());
    assertEquals(0,selected(d));
  }
  @Test public void twoNearbyHeroKillsStayTwoSeparateSegments() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,4,true),k(10330,5,true)),
      Arrays.asList(b(10100,"OCR พบคิล: double kill")),
      Collections.emptyList());
    assertEquals(2,selected(d));
    ArrayList<Long> marks=new ArrayList<>();
    for(KillReconcilerV7.Decision x:d)if(x.selected)marks.add(x.atMs);
    assertEquals(2,HighlightPlanner.calculate(marks,30000).size());
  }
  @Test public void arbitraryEightOrTenAreSupportedNotFixedCounts(){
    for(int n:new int[]{1,2,8,10,20}) {
      List<KdaCounter.Kill> k=new ArrayList<>();
      for(int i=0;i<n;i++)k.add(k(5000+i*5000L,i+1,true));
      assertEquals(n,selected(KillReconcilerV7.reconcile(k,
          Collections.emptyList(),Collections.emptyList())));
    }
  }
  @Test public void swordZeroToOneThenOneToTwoOnlyTwoClips() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(15000,1,true),k(42000,2,true)),
      Arrays.asList(b(15050,"enemy double kill"),b(16900,"monster"),
        b(30000,"you have slain an enemy hero"),b(43000,"objective:overlord")),
      Arrays.asList(28000L));
    assertEquals(2,selected(d));assertEquals(2,d.size());
    assertEquals(15000L,d.get(0).atMs);
    assertEquals(42000L,d.get(1).atMs);
    List<HighlightPlanner.Range> cuts=HighlightPlanner.calculate(
      Arrays.asList(d.get(0).atMs,d.get(1).atMs),60000L);
    assertEquals(10000L,cuts.get(0).startMs);
    assertEquals(18000L,cuts.get(0).endMs);
    assertEquals(37000L,cuts.get(1).startMs);
    assertEquals(45000L,cuts.get(1).endMs);
  }
  @Test public void swordJumpWithoutIntermediateTimestampsIsReviewOnly() {
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.829f,.060f);
    for(int i=0;i<3;i++)assertTrue(t.feed(400L*i,null,0).isEmpty());
    assertTrue(t.feed(10000L,null,2).isEmpty());
    assertTrue(t.feed(10400L,null,2).isEmpty());
    List<KdaCounter.Kill> jumps=t.feed(10800L,null,2);
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
        jumps,Collections.emptyList(),Collections.emptyList());
    assertEquals(2,d.size());
    assertEquals(0,selected(d));
  }

  @Test public void bannersWithoutKIncrementProduceNothing() {
    assertTrue(KillReconcilerV7.reconcile(Collections.emptyList(),
      Arrays.asList(b(10000,"double kill"),b(13000,"objective:tyrant"),
       b(17000,"you have slain an enemy hero")),Collections.emptyList()).isEmpty());
  }
  @Test public void enemyDoubleKillAndBossNameAreNotHeroEvidence(){
    assertFalse(b(0,"enemy double kill").heroicText());
    assertFalse(b(0,"you have slain the storm dragon").heroicText());
    assertFalse(b(0,"you have been slain").heroicText());
    assertTrue(b(0,"you have slain an enemy hero").heroicText());
  }
}
