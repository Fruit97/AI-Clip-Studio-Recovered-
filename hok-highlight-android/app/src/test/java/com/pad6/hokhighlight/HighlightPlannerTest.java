package com.pad6.hokhighlight;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
public class HighlightPlannerTest {
 @Test public void fiveSecondsBeforeAndOneAfter() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(15000L,48000L),60000L);
   assertEquals(2,r.size());
   assertEquals(10000L,r.get(0).startMs);assertEquals(16000L,r.get(0).endMs);
   assertEquals(43000L,r.get(1).startMs);assertEquals(49000L,r.get(1).endMs);
   assertEquals(6000L,r.get(0).endMs-r.get(0).startMs);
 }
 @Test public void consecutiveKillsProduceSeparateRawRanges() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(
       Arrays.asList(10000L,11000L,14000L),60000L);
   assertEquals(3,r.size());
   assertEquals(5000L,r.get(0).startMs);assertEquals(11000L,r.get(0).endMs);
   assertEquals(6000L,r.get(1).startMs);assertEquals(12000L,r.get(1).endMs);
   assertEquals(9000L,r.get(2).startMs);assertEquals(15000L,r.get(2).endMs);
 }
 @Test public void arbitraryKillCountsAreNeverHardcoded() {
   for(int n:new int[]{1,2,8,10,17}) {
     java.util.List<Long> times=new java.util.ArrayList<>();
     for(int i=0;i<n;i++)times.add(6000L+7000L*i);
     assertEquals(n,HighlightPlanner.calculate(times,180000L).size());
   }
 }
 @Test public void startAndEndAreClamped() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(
       Arrays.asList(1000L,59000L),60000L);
   assertEquals(0L,r.get(0).startMs);assertEquals(2000L,r.get(0).endMs);
   assertEquals(54000L,r.get(1).startMs);assertEquals(60000L,r.get(1).endMs);
 }
 @Test public void noKills() {
   assertTrue(HighlightPlanner.calculate(Collections.emptyList(),60000L).isEmpty());
 }
 @Test public void ownDeathInFiveSecondLeadIsNotExported() {
   assertTrue(HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L),Arrays.asList(8000L),30000L).isEmpty());
 }
 @Test public void noNearbyDeathKeepsExactlySixSeconds() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(20000L),Arrays.asList(7000L,26000L),60000L);
   assertEquals(1,r.size());
   assertEquals(15000L,r.get(0).startMs);assertEquals(21000L,r.get(0).endMs);
 }
 @Test public void sourceBeginningClampsFiveSecondPreRoll() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculate(Arrays.asList(1500L),20000L);
   assertEquals(0L,r.get(0).startMs);assertEquals(2500L,r.get(0).endMs);
 }
 @Test public void closeKillsMergeWithoutReplayingTheSameFight() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,11000L,14000L),Collections.emptyList(),60000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);assertEquals(15000L,r.get(0).endMs);
 }
 @Test public void distantKillsMakeSeparateSequentialCuts() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,40000L),Collections.emptyList(),60000L);
   assertEquals(2,r.size());
   assertEquals(5000L,r.get(0).startMs);assertEquals(11000L,r.get(0).endMs);
   assertEquals(35000L,r.get(1).startMs);assertEquals(41000L,r.get(1).endMs);
 }
 @Test public void noKillOrOnlyOwnDeathDoesNotExport() {
   assertTrue(HighlightPlanner.planFinalVideo(
       Collections.emptyList(),Arrays.asList(15000L),60000L).isEmpty());
   assertTrue(HighlightPlanner.planFinalVideo(
       Arrays.asList(12000L),Arrays.asList(11000L),60000L).isEmpty());
 }
 @Test public void postKillDeathTrimmingRemainsAfterMerging() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,10300L),Arrays.asList(11200L),60000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);assertEquals(11000L,r.get(0).endMs);
 }
 @Test public void separateClipsNeverRepeatSourceTime() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,11000L,25000L,40000L),
       Collections.emptyList(),60000L);
   assertEquals(3,r.size());
   for(int i=1;i<r.size();i++)assertTrue(r.get(i).startMs>r.get(i-1).endMs);
   long duration=0L;for(HighlightPlanner.Range v:r)duration+=v.endMs-v.startMs;
   assertEquals(7000L+6000L+6000L,duration);
 }
 @Test public void keepV81FightGroupingWhenKillsAreSevenSecondsApart() {
   // V8.1 grouped these kills because its original after-tail was 3s.
   // The shorter end-tail must NOT split that formerly continuous fight.
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(10000L,17000L),Collections.emptyList(),60000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);
   assertEquals(18000L,r.get(0).endMs);
 }
 @Test public void nullMarkersAreIgnored() {
   assertEquals(2,HighlightPlanner.calculate(
       Arrays.asList(10000L,null,20000L),30000L).size());
 }
 @Test public void deathInsideOneSecondPostKillTailIsTrimmed() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L),Arrays.asList(10900L),30000L);
   assertEquals(1,r.size());
   assertEquals(5000L,r.get(0).startMs);assertEquals(10100L,r.get(0).endMs);
 }
 @Test public void severalHeroKillRangesAreStillDistinctBeforeMerge() {
   List<HighlightPlanner.Range> r=HighlightPlanner.calculateAvoidDeaths(
       Arrays.asList(10000L,11000L,19000L),Arrays.asList(13000L),30000L);
   assertEquals(3,r.size());
   assertEquals(12000L,r.get(1).endMs);assertEquals(20000L,r.get(2).endMs);
 }
 @Test public void killAtOneMinuteTwentyRunsToOneTwentyOne() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(80000L),Collections.emptyList(),120000L);
   assertEquals(1,r.size());
   assertEquals(75000L,r.get(0).startMs);assertEquals(81000L,r.get(0).endMs);
 }
 @Test public void adjacentKillsExtendContinuousFightOnlyAsNeeded() {
   List<HighlightPlanner.Range> r=HighlightPlanner.planFinalVideo(
       Arrays.asList(80000L,81000L),Collections.emptyList(),120000L);
   assertEquals(1,r.size());
   assertEquals(75000L,r.get(0).startMs);assertEquals(82000L,r.get(0).endMs);
 }
}
