package com.pad6.hokhighlight;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class KdaCounterTest {
  static KdaCounter.Observation score(int kills,int deaths,int assists) {
    return new KdaCounter.Observation(kills,deaths,assists,.79f,.048f);
  }
  static List<KdaCounter.Kill> confirm(KdaCounter.Tracker tracker,long at,
                                     int kills,int deaths,int assists) {
    tracker.feed(at,score(kills,deaths,assists));
    return tracker.feed(at+800,score(kills,deaths,assists));
  }
  @Test public void topRightKdaTripletExcludesTeamScore() {
    List<KdaCounter.NumberBox> b=Arrays.asList(
      new KdaCounter.NumberBox(13,.50f,.045f),
      new KdaCounter.NumberBox(14,.58f,.045f),
      new KdaCounter.NumberBox(7,.69f,.048f),
      new KdaCounter.NumberBox(3,.77f,.048f),
      new KdaCounter.NumberBox(0,.85f,.048f));
    KdaCounter.Observation found=KdaCounter.parse(b);
    assertNotNull(found);assertEquals(7,found.kills);
    assertEquals(3,found.deaths);assertEquals(0,found.assists);
  }
  @Test public void invalidOrUnstableOcrIsNotAShot() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    assertTrue(confirm(t,0,2,1,0).isEmpty());
    assertTrue(t.feed(2000,score(9,1,0)).isEmpty());
    assertTrue(t.feed(2800,score(2,1,0)).isEmpty());
    assertTrue(t.feed(3600,score(2,1,0)).isEmpty());
    assertEquals(1,confirm(t,4200,3,1,0).size());
  }
  @Test public void jungleMonstersDoNotChangePersonalKda() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    assertTrue(confirm(t,0,2,1,0).isEmpty());
    assertTrue(confirm(t,3000,2,1,0).isEmpty());
    assertTrue(confirm(t,6000,2,1,0).isEmpty());
    assertEquals(1,confirm(t,9000,3,1,0).size());
  }
  @Test public void killsWithinSameSecondAreSeparateEvents() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,0,0,0);
    List<KdaCounter.Kill> kills=confirm(t,3000,2,0,0);
    assertEquals(2,kills.size());
    assertTrue(kills.get(0).atMs<kills.get(1).atMs);
    assertEquals(1,kills.get(0).individualTotal);
    assertEquals(2,kills.get(1).individualTotal);
  }
  @Test public void eightOrTenKillsYieldExactlyEightOrTenEvents() {
    for(int target:new int[]{8,10}) {
      KdaCounter.Tracker t=new KdaCounter.Tracker();
      confirm(t,0,0,0,0);
      int total=0;
      for(int k=1;k<=target;k++)total+=confirm(t,k*5000L,k,k/6,k/3).size();
      assertEquals(target,total);
    }
  }
  @Test public void increasedDeathsOrAssistsNeverAddKillHighlights() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,1,0,0);
    assertTrue(confirm(t,2500,1,1,3).isEmpty());
    assertTrue(confirm(t,5000,1,2,4).isEmpty());
    assertEquals(1,confirm(t,8000,2,2,4).size());
  }
  @Test public void invalidScoreboardReadCannotCreateTenFakeKills() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,1,0,0);
    assertTrue(confirm(t,5000,20,0,0).isEmpty());
    assertEquals(1,confirm(t,10000,2,0,0).size());
  }
  @Test public void missingKdaDoesNotCreateFakeKills() {
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    confirm(t,0,4,1,2);
    assertTrue(t.feed(2000,null).isEmpty());
    assertTrue(t.feed(3000,null).isEmpty());
    assertTrue(confirm(t,5000,4,1,2).isEmpty());
  }
}
