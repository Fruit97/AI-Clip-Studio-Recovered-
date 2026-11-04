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

  @Test public void rejectsUntrustedLooseNumericGroupAsCertifiedKill() {
    KdaCounter.Observation weak=KdaCounter.parse(Arrays.asList(
      new KdaCounter.NumberBox(3,.60f,.052f),
      new KdaCounter.NumberBox(1,.67f,.052f),
      new KdaCounter.NumberBox(4,.74f,.052f)));
    assertNotNull(weak);
    assertFalse(weak.trusted);
    KdaCounter.Tracker t=new KdaCounter.Tracker();
    for(int i=0;i<5;i++) assertTrue(t.feed(i*400,weak).isEmpty());
    assertFalse(t.isCalibrated());
    assertEquals(5,t.rejectedUntrusted());
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
