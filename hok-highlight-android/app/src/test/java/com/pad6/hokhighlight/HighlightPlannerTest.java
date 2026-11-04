package com.pad6.hokhighlight;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
public class HighlightPlannerTest {
 @Test public void fiveSecondsBeforeAndThreeAfter() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(15000L,48000L),60000);
   assertEquals(2,r.size()); assertEquals(10000,r.get(0).startMs);assertEquals(18000,r.get(0).endMs);
   assertEquals(43000L,r.get(1).startMs);assertEquals(51000L,r.get(1).endMs);
   assertEquals(8000L,r.get(0).endMs-r.get(0).startMs);
 }
 @Test public void consecutiveKillsMakeSeparateShotsEvenIfOverlapping() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(10000L,11000L,14000L),60000);
   assertEquals(3,r.size());
   assertEquals(5000,r.get(0).startMs);assertEquals(13000,r.get(0).endMs);
   assertEquals(6000,r.get(1).startMs);assertEquals(14000,r.get(1).endMs);
   assertEquals(9000,r.get(2).startMs);assertEquals(17000,r.get(2).endMs);
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
 @Test public void deathBeforeKillInFiveSecondLeadDoesNotExportDeathScreen() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L),Arrays.asList(8000L),30000L);
   assertTrue(r.isEmpty());
 }
 @Test public void noDeathNearKillAlwaysKeepsExactlyEightSeconds() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(20000L),Arrays.asList(7000L,26000L),60000L);
   assertEquals(1,r.size());
   assertEquals(15000L,r.get(0).startMs);
   assertEquals(23000L,r.get(0).endMs);
 }
 @Test public void sourceClampsFiveSecondPrerollAtBeginning() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(1500L),20000L);
   assertEquals(0L,r.get(0).startMs);assertEquals(4500L,r.get(0).endMs);
 }
 @Test public void closeKillsMergeIntoSingleContinuousFightNoRepeatedFrames() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,11000L,14000L),Collections.emptyList(),60000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);
   assertEquals(17000L,r.get(0).endMs);
 }
 @Test public void distantKillsBecomeSeparateSequentialClips() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,40000L),Collections.emptyList(),60000L);
   assertEquals(2,r.size());
   assertEquals(5000L,r.get(0).startMs);
   assertEquals(13000L,r.get(0).endMs);
   assertEquals(35000L,r.get(1).startMs);
   assertEquals(43000L,r.get(1).endMs);
 }
 @Test public void noKillOrOnlyOwnDeathNeverExports() {
   assertTrue(HighlightPlanner.planFinalVideo(
       Collections.emptyList(),Arrays.asList(15000L),60000L).isEmpty());
   assertTrue(HighlightPlanner.planFinalVideo(
       Arrays.asList(12000L),Arrays.asList(11000L),60000L).isEmpty());
 }
 @Test public void postKillDeathTrimIsKeptThroughMerging() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,10500L),Arrays.asList(12000L),60000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);
   assertEquals(11200L,r.get(0).endMs);
 }
 @Test public void separateClipsDoNotRepeatSameSourceTime() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,11000L,25000L,40000L),
       Collections.emptyList(),60000L);
   assertEquals(3,r.size());
   for(int i=1;i<r.size();i++)assertTrue(r.get(i).startMs>r.get(i-1).endMs);
   long output=0;for(HighlightPlanner.Range v:r)output+=v.endMs-v.startMs;
   assertEquals(9000L+8000L+8000L,output);
 }
 @Test public void nullMarkersAreIgnored() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(
       Arrays.asList(10000L,null,20000L),30000L);
   assertEquals(2,r.size());
 }
 @Test public void deathInsidePostKillTailIsTrimmedBeforeDeath() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L),Arrays.asList(12000L),30000);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);
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
