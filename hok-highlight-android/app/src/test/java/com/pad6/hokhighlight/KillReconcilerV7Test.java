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
  @Test public void deathClipIsNotAPlayerKill() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(9000,3,true)),
      Arrays.asList(b(9200,"OCR พบคิล: You have slain an enemy hero")),
      Arrays.asList(9800L));
    assertEquals(0,selected(d));
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
  @Test public void weakKdaPlusHeroSpecificTextCanBeSelected() {
    List<KillReconcilerV7.Decision> d=KillReconcilerV7.reconcile(
      Arrays.asList(k(10000,2,false)),
      Arrays.asList(b(10200,"ข้อความประกาศคิล: double kill")),
      Collections.emptyList());
    assertEquals(1,selected(d));assertEquals(10200,d.get(0).atMs);
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
  @Test public void enemyDoubleKillAndBossNameAreNotHeroEvidence(){
    assertFalse(b(0,"enemy double kill").heroicText());
    assertFalse(b(0,"you have slain the storm dragon").heroicText());
    assertFalse(b(0,"you have been slain").heroicText());
    assertTrue(b(0,"you have slain an enemy hero").heroicText());
  }
}
