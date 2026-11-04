package com.pad6.hokhighlight;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.List;

public class KdaCounterTest {
  private static KdaCounter.Observation score(int k,int d,int a) {
    return new KdaCounter.Observation(k,d,a,.67f,.052f);
  }
  private static List<KdaCounter.Kill> confirm(
      KdaCounter.Tracker t,long at,int k,int d,int a) {
    assertTrue(t.feed(at,score(k,d,a)).isEmpty());
    assertTrue(t.feed(at+800,score(k,d,a)).isEmpty());
    return t.feed(at+1600,score(k,d,a));
  }

  @Test public void recognizesPersonalKdaNearHeaderNotArbitraryRightmostNumbers() {
    List<KdaCounter.NumberBox> boxes=Arrays.asList(
      new KdaCounter.NumberBox(13,.600f,.048f), // team score
      new KdaCounter.NumberBox(14,.690f,.048f), // opponent score
      new KdaCounter.NumberBox(7,.829f,.052f), // personal K
      new KdaCounter.NumberBox(3,.867f,.052f), // personal D
      new KdaCounter.NumberBox(0,.905f,.052f), // personal A
      new KdaCounter.NumberBox(30,.795f,.025f)); // FPS
    KdaCounter.Observation obs=KdaCounter.parse(boxes);
    assertNotNull(obs);
    assertEquals(7,obs.kills);
    assertEquals(3,obs.deaths);
    assertEquals(0,obs.assists);
  }

  @Test public void swordZeroOneTwoWithAssistAndDeathUnchanged() {
    KdaCounter.Tracker tracker=new KdaCounter.Tracker();
    KdaCounter.Observation zero=new KdaCounter.Observation(0,0,0,.867f,.052f,false);
    for(int i=0;i<5;i++)assertTrue(tracker.feed(400L*i,zero).isEmpty());
    KdaCounter.Observation one=new KdaCounter.Observation(1,0,0,.867f,.052f,false);
    List<KdaCounter.Kill> first=java.util.Collections.emptyList();
    for(int i=0;i<3;i++)first=tracker.feed(10000L+i*400L,one);
    assertEquals(1,first.size());assertEquals(1,first.get(0).individualTotal);
    assertTrue(first.get(0).trustedHud);
    KdaCounter.Observation assist=new KdaCounter.Observation(1,0,1,.867f,.052f,false);
    for(int i=0;i<3;i++)assertTrue(tracker.feed(14000L+i*400L,assist).isEmpty());
    KdaCounter.Observation two=new KdaCounter.Observation(2,0,1,.867f,.052f,false);
    List<KdaCounter.Kill> second=java.util.Collections.emptyList();
    for(int i=0;i<3;i++)second=tracker.feed(30000L+i*400L,two);
    assertEquals(1,second.size());assertEquals(2,second.get(0).individualTotal);
  }
  @Test public void scoreboardDigitsAreNotPersonalKda() {
    assertNull(KdaCounter.parse(Arrays.asList(
      new KdaCounter.NumberBox(5,.56f,.05f),
      new KdaCounter.NumberBox(2,.62f,.05f),
      new KdaCounter.NumberBox(8,.69f,.05f))));
  }

  @Test public void replayReferenceHudThreePersonalKillsOneDeath() {
    // Screen values inspected in 24218.mp4, not on-device ML Kit outputs.
    KdaCounter.Tracker tracker=new KdaCounter.Tracker();
    KdaCounter.Observation base=KdaCounter.parse(Arrays.asList(
      new KdaCounter.NumberBox(0,.829f,.052f),
      new KdaCounter.NumberBox(0,.867f,.052f),
      new KdaCounter.NumberBox(0,.905f,.052f)));
    assertNotNull(base);
    for(int i=0;i<5;i++)assertTrue(tracker.feed(400L*i,base).isEmpty());
    int[][] values={{1,0,0},{1,1,0},{2,1,0},{3,1,0}};
    long[] timestamps={40000,100000,190000,235000};
    int count=0;
    for(int j=0;j<values.length;j++){
      int[] v=values[j];
      KdaCounter.Observation o=KdaCounter.parse(Arrays.asList(
        new KdaCounter.NumberBox(v[0],.829f,.052f),
        new KdaCounter.NumberBox(v[1],.867f,.052f),
        new KdaCounter.NumberBox(v[2],.905f,.052f)));
      List<KdaCounter.Kill> found=java.util.Collections.emptyList();
      for(int i=0;i<3;i++)found=tracker.feed(timestamps[j]+400L*i,o);
      for(KdaCounter.Kill k:found)assertTrue(k.trustedHud);
      count+=found.size();
    }
    assertEquals(3,count);
    assertEquals(1,tracker.deathsIgnored());
  }

  @Test public void noThreeCountersMustNotInventAKill() {
    assertNull(KdaCounter.parse(Arrays.asList(
      new KdaCounter.NumberBox(10,.42f,.06f),
      new KdaCounter.NumberBox(8,.49f,.06f))));
  }

  @Test public void oneHeroKillOnlyWhenPersonalKIncreases() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    assertTrue(confirm(t,0,2,0,1).isEmpty());
    assertTrue(confirm(t,3000,2,0,1).isEmpty());
    List<KdaCounter.Kill> got=confirm(t,6000,3,0,1);
    assertEquals(1,got.size());
    assertEquals(3,got.get(0).individualTotal);
  }

  @Test public void deathOnlyNeverProducesHighlight() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,2,0,1);
    assertTrue(confirm(t,3500,2,1,1).isEmpty());
    assertEquals(1,t.deathsIgnored());
    assertEquals(0,t.ambiguousEvents());
    assertEquals(1,confirm(t,7000,3,1,1).size());
  }

  @Test public void deathAndKillInSameBlindIntervalAreNotAutomaticallyExported() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,2,0,1);
    assertTrue(confirm(t,5000,3,1,1).isEmpty());
    assertEquals(1,t.ambiguousEvents());
    assertEquals(1,t.deathsIgnored());
    assertEquals(1,confirm(t,9000,4,1,1).size());
  }

  @Test public void monsterKillsAndAssistsDontMakeHighlights() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,2,0,1);
    assertTrue(confirm(t,2000,2,0,1).isEmpty());
    assertTrue(confirm(t,4500,2,0,2).isEmpty());
    assertTrue(confirm(t,7300,2,0,2).isEmpty());
    assertEquals(1,confirm(t,11000,3,0,2).size());
  }

  @Test public void twoKillsCloseTogetherAreTwoShotsAndNotMerged() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,0,0,0);
    List<KdaCounter.Kill> found=confirm(t,3600,2,0,0);
    assertEquals(2,found.size());
    assertTrue(found.get(0).atMs<found.get(1).atMs);
    assertEquals(1,found.get(0).individualTotal);
    assertEquals(2,found.get(1).individualTotal);
    assertEquals(2,HighlightPlanner.calculate(
      Arrays.asList(found.get(0).atMs,found.get(1).atMs),30000).size());
  }

  @Test public void countsEightOrTenActualKillsWithoutHardcodedTargets() {
    for(int n:new int[]{8,10,17}){
      KdaCounter.Tracker t=new KdaCounter.Tracker();
      confirm(t,0,0,0,0);
      int total=0;
      for(int k=1;k<=n;k++)
        total+=confirm(t,3000L*k,k,k/5,k/3).size();
      // K and D in the same interval are ambiguous, so this setup should
      // NOT claim every kill is confirmed. The user's safety rule wins.
      assertEquals(n-n/5,total);
    }
  }

  @Test public void countsEightOrTenPureKillsCorrectly() {
    for(int n:new int[]{8,10,17}){
      KdaCounter.Tracker t=new KdaCounter.Tracker();
      confirm(t,0,0,0,0);
      int total=0;
      for(int k=1;k<=n;k++)
        total+=confirm(t,3000L*k,k,0,k/3).size();
      assertEquals(n,total);
    }
  }

  @Test public void rejectsTemporaryOcrErrorAndWrongHudLocation() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,3,1,2);
    assertTrue(t.feed(2000,score(25,1,2)).isEmpty());
    assertTrue(t.feed(2800,score(3,1,2)).isEmpty());
    assertTrue(t.feed(4000,new KdaCounter.Observation(4,1,2,.86f,.09f)).isEmpty());
    assertEquals(1,confirm(t,5200,4,1,2).size());
  }

  @Test public void rejectsDeathCounterReadAsKillWhenKdaShifts() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,1,0,0);
    KdaCounter.Observation shifted=new KdaCounter.Observation(2,1,0,.76f,.06f);
    assertTrue(t.feed(3000,shifted).isEmpty());
    assertTrue(t.feed(3800,shifted).isEmpty());
    assertTrue(t.feed(4600,shifted).isEmpty());
    assertEquals(1,confirm(t,6400,2,0,0).size());
  }
}
