package com.pad6.hokhighlight;

import org.junit.Test;
import java.util.List;
import static org.junit.Assert.*;

public class SwordCounterTrackerTest {
  private static KdaCounter.Observation full(int k,int d,int a){
    return new KdaCounter.Observation(k,d,a,.867f,.072f,false);
  }
  private static void calibrate(SwordCounterTracker t){
    assertTrue(t.feed(0,full(0,0,0),-1).isEmpty());
    assertTrue(t.feed(400,full(0,0,0),-1).isEmpty());
    assertTrue(t.feed(800,full(0,0,0),-1).isEmpty());
    assertTrue(t.hasLocation());
    assertEquals(0,t.confirmedKills());
  }
  private static List<KdaCounter.Kill> read(SwordCounterTracker t,long at,int k){
    assertTrue(t.feed(at,null,k).isEmpty());
    assertTrue(t.feed(at+400,null,k).isEmpty());
    return t.feed(at+800,null,k);
  }
  @Test public void swordZeroOneTwoThroughTenEvenWhenSkullFistOcrDisappear(){
    SwordCounterTracker t=new SwordCounterTracker();
    calibrate(t);
    int total=0;
    for(int k=1;k<=10;k++){
      List<KdaCounter.Kill> found=read(t,k*4000L,k);
      assertEquals("K="+k,1,found.size());
      assertTrue(found.get(0).trustedHud);
      assertEquals(k,found.get(0).individualTotal);
      total+=found.size();
    }
    assertEquals(10,total);
  }
  @Test public void singleSpuriousKDoesNotCreateHighlight(){
    SwordCounterTracker t=new SwordCounterTracker();
    calibrate(t);
    assertTrue(t.feed(3000,null,4).isEmpty());
    assertTrue(t.feed(3400,null,0).isEmpty());
    assertTrue(t.feed(3800,null,1).isEmpty());
    assertTrue(t.feed(4200,null,0).isEmpty());
    assertEquals(0,t.confirmedKills());
    assertEquals(1,read(t,5000,1).size());
  }
  @Test public void skullAndFistChangesWithSameSwordMakeNoCuts(){
    SwordCounterTracker t=new SwordCounterTracker();
    calibrate(t);
    assertTrue(t.feed(4000,full(0,1,0),0).isEmpty());
    assertTrue(t.feed(4400,full(0,1,0),0).isEmpty());
    assertTrue(t.feed(4800,full(0,1,0),0).isEmpty());
    assertEquals(0,t.confirmedKills());
    assertEquals(1,read(t,6000,1).size());
  }
  @Test public void conflictingFullHudAndSwordReadingCannotCreateCut(){
    SwordCounterTracker t=new SwordCounterTracker();
    calibrate(t);
    for(int i=0;i<5;i++)
      assertTrue(t.feed(4000+i*400L,full(0,0,0),1).isEmpty());
    assertEquals(0,t.confirmedKills());
    assertEquals(1,read(t,8000,1).size());
  }
  @Test public void manuallyPinSwordAndReadZeroToTenWithoutFullKda(){
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.821f,.071f);
    assertTrue(t.isPinned());assertTrue(t.hasLocation());
    assertEquals(.821f,t.swordX(),.00001f);
    for(int i=0;i<3;i++)
      assertTrue(t.feed(i*400L,null,0).isEmpty());
    assertEquals(0,t.confirmedKills());
    for(int k=1;k<=10;k++) {
      List<KdaCounter.Kill> found=read(t,3000L*k,k);
      assertEquals(1,found.size());
      assertEquals(k,found.get(0).individualTotal);
      assertTrue(found.get(0).trustedHud);
    }
  }

  @Test public void pinnedFirstNumberIsBaselineNotInventedKill(){
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.79f,.080f);
    for(int i=0;i<3;i++)assertTrue(t.feed(i*400L,null,5).isEmpty());
    assertEquals(5,t.confirmedKills());
    assertEquals(1,read(t,8000L,6).size());
  }

  @Test public void pinnedFullOcrOnlyHelpsAtSameSwordNumberLocation(){
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.827f,.070f);
    KdaCounter.Observation near=new KdaCounter.Observation(
        0,0,0,.867f,.070f,false,.827f);
    for(int i=0;i<3;i++)assertTrue(t.feed(i*400L,near,-1).isEmpty());
    assertEquals(0,t.confirmedKills());
    KdaCounter.Observation wrong=new KdaCounter.Observation(
        9,0,0,.715f,.070f,false,.675f);
    for(int i=0;i<5;i++)assertTrue(t.feed(3000L+i*400L,wrong,-1).isEmpty());
    assertEquals(0,t.confirmedKills());
  }

  @Test public void twoKilledBetweenSamplesAreReviewOnlyNotGuessed(){
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.829f,.065f);
    for(int i=0;i<3;i++)t.feed(i*400L,null,0);
    List<KdaCounter.Kill> found=read(t,10000L,2);
    assertEquals(2,found.size());
    assertFalse(found.get(0).trustedHud);
    assertFalse(found.get(1).trustedHud);
    assertTrue(found.get(0).inferred);
    assertTrue(found.get(1).inferred);
  }

  @Test public void autoHudLockSurvivesIntermittentMissingFrames(){
    SwordCounterTracker t=new SwordCounterTracker();
    assertTrue(t.feed(0L,full(0,0,0),-1).isEmpty());
    for(int i=1;i<=6;i++)
      assertTrue(t.feed(i*400L,null,-1).isEmpty());
    assertTrue(t.feed(3200L,full(0,0,0),-1).isEmpty());
    assertTrue(t.feed(6400L,full(0,0,0),-1).isEmpty());
    assertTrue(t.hasLocation());
    assertEquals(0,t.confirmedKills());
    List<KdaCounter.Kill> found=read(t,10000L,1);
    assertEquals(1,found.size());
    assertEquals(1,found.get(0).individualTotal);
  }

  @Test public void pinnedNoiseAndDeathsDoNotCreateKill(){
    SwordCounterTracker t=new SwordCounterTracker();
    t.pinSword(.825f,.075f);
    for(int i=0;i<3;i++)t.feed(i*400L,null,0);
    for(int i=0;i<5;i++)
      assertTrue(t.feed(4000L+i*400L,null,0).isEmpty());
    assertTrue(t.feed(8000L,null,7).isEmpty());
    assertTrue(t.feed(8400L,null,0).isEmpty());
    assertEquals(0,t.confirmedKills());
  }

  @Test public void unlocatedNumbersNeverBecomeCuts(){
    SwordCounterTracker t=new SwordCounterTracker();
    for(int i=0;i<9;i++)
      assertTrue(t.feed(i*400L,null,20).isEmpty());
    assertFalse(t.hasLocation());
    assertEquals(-1,t.confirmedKills());
  }
  @Test public void readingDecreasesAndHugeJumpsAreNoise(){
    SwordCounterTracker t=new SwordCounterTracker();
    calibrate(t);
    assertEquals(1,read(t,4000,1).size());
    assertTrue(t.feed(9000,null,0).isEmpty());
    assertTrue(t.feed(9400,null,0).isEmpty());
    assertTrue(t.feed(9800,null,0).isEmpty());
    assertTrue(t.feed(11000,null,19).isEmpty());
    assertEquals(1,t.confirmedKills());
    assertTrue(t.ignoredNoise()>0);
  }
}
