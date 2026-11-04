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
 @Test public void consecutiveKillsMakeSeparateShotsEvenIfOverlapping() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(10000L,11000L,14000L),60000);
   assertEquals(3,r.size());
   assertEquals(7000,r.get(0).startMs);assertEquals(13000,r.get(0).endMs);
   assertEquals(8000,r.get(1).startMs);assertEquals(14000,r.get(1).endMs);
   assertEquals(11000,r.get(2).startMs);assertEquals(17000,r.get(2).endMs);
 }
 @Test public void arbitraryKillCountsAreNeverHardcoded() {
   for(int count:new int[]{1,2,8,10,17}) {
     java.util.List<Long> times=new java.util.ArrayList<>();
     for(int i=0;i<count;i++)times.add(6000L+7000L*i);
     assertEquals(count,HighlightPlanner.calculate(times,180000).size());
   }
 }
 @Test public void startAndEndAreClamped() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(1000L,59000L),60000);
   assertEquals(0,r.get(0).startMs);assertEquals(60000,r.get(1).endMs);
 }
 @Test public void noKills() {assertTrue(HighlightPlanner.calculate(Collections.emptyList(),60000).isEmpty());}
 @Test public void deathInsidePostKillTailIsTrimmedBeforeDeath() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L),Arrays.asList(12000L),30000);
   assertEquals(1,r.size());
   assertEquals(7000L,r.get(0).startMs);
   assertEquals(11200L,r.get(0).endMs);
 }
 @Test public void severalHeroKillsStaySeparateWithoutShowingDeath(){
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L,11000L,19000L),
       Arrays.asList(13000L),30000L);
   assertEquals(3,r.size());
   assertEquals(12200L,r.get(1).endMs);
   assertEquals(22000L,r.get(2).endMs);
 }

}
