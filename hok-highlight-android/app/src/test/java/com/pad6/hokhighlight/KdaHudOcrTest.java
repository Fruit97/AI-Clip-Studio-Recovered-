package com.pad6.hokhighlight;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class KdaHudOcrTest {
  @Test public void acceptsPersonalSlashSeparatedKda() {
    KdaCounter.Observation obs=KdaHudOcr.parse(Arrays.asList(
      new KdaHudOcr.Line("12:04",.70f,.035f),
      new KdaHudOcr.Line("4/1/7",.76f,.055f),
      new KdaHudOcr.Line("30 FPS",.96f,.035f)));
    assertNotNull(obs);
    assertTrue(obs.trusted);
    assertEquals(4,obs.kills);
    assertEquals(1,obs.deaths);
    assertEquals(7,obs.assists);
  }

  @Test public void distinctDeathChangeDoesNotGenerateOwnKill() {
    KdaCounter.Tracker tracker=new KdaCounter.Tracker();
    long t=0;
    KdaCounter.Observation initial=KdaHudOcr.parse(
      Collections.singletonList(new KdaHudOcr.Line("3/0/1",.76f,.055f)));
    for(int i=0;i<3;i++) assertTrue(tracker.feed(t+i*400,initial).isEmpty());
    KdaCounter.Observation died=KdaHudOcr.parse(
      Collections.singletonList(new KdaHudOcr.Line("3 / 1 / 1",.76f,.055f)));
    for(int i=0;i<3;i++) assertTrue(tracker.feed(2400+i*400,died).isEmpty());
    assertEquals(1,tracker.deathsIgnored());
    assertTrue(tracker.deathMoments().size()==1);
  }

  @Test public void rejectsClockTeamScoreOrRandomNumbers() {
    assertNull(KdaHudOcr.parse(Arrays.asList(
      new KdaHudOcr.Line("12:48",.78f,.04f),
      new KdaHudOcr.Line("27 VS 18",.62f,.045f),
      new KdaHudOcr.Line("30 FPS",.94f,.04f))));
    assertNull(KdaHudOcr.parse(Collections.singletonList(
      new KdaHudOcr.Line("8/1/3",.20f,.05f))));
    assertNull(KdaHudOcr.parse(Collections.singletonList(
      new KdaHudOcr.Line("8/1/3",.80f,.62f))));
  }

  @Test public void acceptsSlashVariantsAndMultipleDigits() {
    KdaCounter.Observation obs=KdaHudOcr.parse(Arrays.asList(
      new KdaHudOcr.Line("16 | 2 | 11",.73f,.045f)));
    assertNotNull(obs);assertEquals(16,obs.kills);
    assertEquals(2,obs.deaths);assertEquals(11,obs.assists);
  }

  @Test public void calibratedSeparateDigitsCanReadRealHudWithoutSlashes() {
    List<KdaHudOcr.Line> source=Arrays.asList(
       new KdaHudOcr.Line("11:34",.62f,.035f),
       new KdaHudOcr.Line("3",.829f,.052f),
       new KdaHudOcr.Line("1",.867f,.052f),
       new KdaHudOcr.Line("4",.905f,.052f),
       new KdaHudOcr.Line("30 FPS",.795f,.025f));
    KdaCounter.Observation weak=KdaHudOcr.parse(source);
    assertNotNull(weak);
    assertFalse(weak.trusted);
    assertEquals(3,weak.kills);
    assertEquals(1,weak.deaths);
    assertEquals(4,weak.assists);
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    for(int i=0;i<4;i++) assertTrue(t.feed(i*400,weak).isEmpty());
    assertFalse("A one-off numeral group is never sufficient",t.isCalibrated());
    assertTrue(t.feed(1600,weak).isEmpty());
    assertTrue(t.isCalibrated());

    KdaCounter.Observation death=new KdaCounter.Observation(3,2,4,.867f,.052f,false);
    for(int i=0;i<3;i++)assertTrue(t.feed(2400+i*400,death).isEmpty());
    assertEquals(1,t.deathsIgnored());

    KdaCounter.Observation kill=new KdaCounter.Observation(4,2,4,.867f,.052f,false);
    List<KdaCounter.Kill> kills=Collections.emptyList();
    for(int i=0;i<3;i++)kills=t.feed(5000+i*400,kill);
    assertEquals(1,kills.size());
  }

  @Test public void zeroReadAsLetterOAndShiftedHudAreSupported() {
    KdaCounter.Observation o=KdaHudOcr.parse(Arrays.asList(
       new KdaHudOcr.Line("O",.702f,.124f),
       new KdaHudOcr.Line("0",.751f,.124f),
       new KdaHudOcr.Line("0",.800f,.124f),
       new KdaHudOcr.Line("FPS 90",.60f,.03f)));
    assertNotNull(o);assertEquals(0,o.kills);
    assertEquals(0,o.deaths);assertEquals(0,o.assists);
  }

  @Test public void lockedSwordDigitCanBeReadWithoutSkullOrFist() {
    List<KdaHudOcr.Line> sparse=Arrays.asList(
      new KdaHudOcr.Line("O",.827f,.072f),
      new KdaHudOcr.Line("FPS 90",.73f,.031f),
      new KdaHudOcr.Line("10",.60f,.04f));
    assertEquals(0,KdaHudOcr.parseSword(sparse,.829f,.072f));
    assertEquals(-1,KdaHudOcr.parseSword(sparse,-1f,-1f));
    assertEquals(-1,KdaHudOcr.parseSword(sparse,.905f,.072f));
    assertEquals(1,KdaHudOcr.parseSingle(" I "));
    assertEquals(10,KdaHudOcr.parseSingle("10"));
    assertEquals(-1,KdaHudOcr.parseSingle("double kill"));
  }
  @Test public void isolatedLooseDigitsCannotTriggerUncalibratedKills() {
    KdaCounter.Observation weak=KdaCounter.parse(Arrays.asList(
      new KdaCounter.NumberBox(3,.829f,.052f),
      new KdaCounter.NumberBox(1,.867f,.052f),
      new KdaCounter.NumberBox(4,.905f,.052f)));
    assertNotNull(weak);assertFalse(weak.trusted);
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    for(int i=0;i<3;i++)assertTrue(t.feed(i*400,weak).isEmpty());
    assertFalse(t.isCalibrated());
  }

  @Test public void doubleKillProducesTwoCutsAndNoMonsterCounter() {
    KdaCounter.Tracker tracker=new KdaCounter.Tracker();
    KdaCounter.Observation start=KdaHudOcr.parse(
      Collections.singletonList(new KdaHudOcr.Line("0/0/0",.76f,.055f)));
    KdaCounter.Observation doubleKill=KdaHudOcr.parse(
      Collections.singletonList(new KdaHudOcr.Line("2/0/0",.76f,.055f)));
    for(int i=0;i<3;i++)tracker.feed(i*400,start);
    List<KdaCounter.Kill> found=Collections.emptyList();
    for(int i=0;i<3;i++)found=tracker.feed(3000+i*400,doubleKill);
    assertEquals(2,found.size());
    assertEquals(2,HighlightPlanner.calculate(
      Arrays.asList(found.get(0).atMs,found.get(1).atMs),20000).size());
  }
}
