package com.pad6.hokhighlight;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
public class HighlightPlannerTest {
 @Test public void threeSecondsBeforeAndAfter() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(15000L,48000L),60000);
   assertEquals(2,r.size()); assertEquals(12000,r.get(0).startMs);assertEquals(18000,r.get(0).endMs);
 }
 @Test public void mergesOverlappingKills() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(10000L,14000L),60000);
   assertEquals(1,r.size());assertEquals(7000,r.get(0).startMs);assertEquals(17000,r.get(0).endMs);
 }
 @Test public void startAndEndAreClamped() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(1000L,59000L),60000);
   assertEquals(0,r.get(0).startMs);assertEquals(60000,r.get(1).endMs);
 }
 @Test public void noKills() {assertTrue(HighlightPlanner.calculate(Collections.emptyList(),60000).isEmpty());}
}
