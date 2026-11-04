package com.pad6.hokhighlight;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class HighlightPlanner {
  private HighlightPlanner() {}
  // One confirmed hero elimination: 5 seconds of approach and 1 second
  // of aftermath, clipped to the source recording boundaries.
  public static final long BEFORE_KILL_MS = 5000L;
  public static final long AFTER_KILL_MS = 1000L;
  public static final long DEATH_SAFETY_MS = 800L;
  public static final class Range {
    public final long startMs;
    public final long endMs;
    public Range(long startMs, long endMs) {
      if (startMs < 0 || endMs <= startMs) throw new IllegalArgumentException("invalid range");
      this.startMs = startMs; this.endMs = endMs;
    }
    public String toString() { return format(startMs)+"–"+format(endMs); }
  }
  public static String format(long ms) {
    long s = Math.max(0,ms)/1000;
    return String.format(java.util.Locale.US,"%02d:%02d",s/60,s%60);
  }
  public static List<Range> calculate(List<Long> killsMs, long videoLengthMs) {
    return calculateWithTail(killsMs,videoLengthMs,AFTER_KILL_MS);
  }
  private static List<Range> calculateWithTail(
      List<Long> killsMs,long videoLengthMs,long tailMs) {
    if (videoLengthMs <= 0) return Collections.emptyList();
    List<Long> sorted = new ArrayList<>();
    if(killsMs!=null) for(Long value:killsMs)
      if(value!=null) sorted.add(value);
    Collections.sort(sorted);
    List<Range> out = new ArrayList<>();
    for (Long when : sorted) {
      if (when == null || when < 0 || when > videoLengthMs) continue;
      long start = Math.max(0, when-BEFORE_KILL_MS);
      long end = Math.min(videoLengthMs,when+tailMs);
      if (end <= start) continue;
      // IMPORTANT: one kill must produce one clip, even if adjacent clips
      // overlap. V1-V4 merged two close kills into one and lost shot count.
      out.add(new Range(start,end));
    }
    return out;
  }
  /**
   * Never include the user's death instead of their confirmed kill.
   * A death after the kill trims the tail before the death overlay.
   * A death in the 5-second pre-roll makes that candidate ambiguous
   * (e.g. a lingering death/respawn screen): leave it out for manual review
   * rather than exporting an unrelated death-only clip.
   */
  public static List<Range> calculateAvoidDeaths(
      List<Long> killsMs,List<Long> deathsMs,long videoLengthMs){
    return calculateAvoidDeathsWithTail(
        killsMs,deathsMs,videoLengthMs,AFTER_KILL_MS);
  }
  private static List<Range> calculateAvoidDeathsWithTail(
      List<Long> killsMs,List<Long> deathsMs,long videoLengthMs,long tailMs){
    if(killsMs==null || killsMs.isEmpty() || videoLengthMs<=0)
      return Collections.emptyList();
    if(deathsMs==null || deathsMs.isEmpty())
      return calculateWithTail(killsMs,videoLengthMs,tailMs);
    List<Long> ordered=new ArrayList<>();
    for(Long value:killsMs)
      if(value!=null && value>=0 && value<=videoLengthMs)ordered.add(value);
    Collections.sort(ordered);
    List<Range> out=new ArrayList<>();
    for(Long killAt:ordered){
      long start=Math.max(0L,killAt-BEFORE_KILL_MS);
      long end=Math.min(videoLengthMs,killAt+tailMs);
      boolean deathInLead=false;
      for(Long deathAt:deathsMs){
        if(deathAt==null)continue;
        if(deathAt<=killAt && deathAt>=start) {
          deathInLead=true;
          break;
        }
        if(deathAt>killAt && deathAt<=end) {
          end=Math.min(end,Math.max(0L,deathAt-DEATH_SAFETY_MS));
        }
      }
      if(!deathInLead && end>start+350L)
        out.add(new Range(start,end));
    }
    return out;
  }

  /**
   * Join touching/overlapping clips into ONE uninterrupted fight. When kills
   * are close together, the old exporter repeated nearly the same 8 seconds
   * per kill; the resulting MP4 appeared to jump backwards. Merge only ranges
   * that overlap or touch. Leave real gaps as hard cuts to the next kill.
   */
  public static List<Range> mergeOverlapping(List<Range> ranges){
    if(ranges==null || ranges.isEmpty())return Collections.emptyList();
    List<Range> sorted=new ArrayList<>(ranges);
    sorted.sort((a,b)->Long.compare(a.startMs,b.startMs));
    List<Range> merged=new ArrayList<>();
    long start=sorted.get(0).startMs,end=sorted.get(0).endMs;
    for(int i=1;i<sorted.size();i++){
      Range next=sorted.get(i);
      if(next.startMs<=end)end=Math.max(end,next.endMs);
      else{
        merged.add(new Range(start,end));
        start=next.startMs;end=next.endMs;
      }
    }
    merged.add(new Range(start,end));
    return merged;
  }

  /**
   * Keep V8.1 fight grouping EXACTLY as before (5s before + 3s after),
   * then shorten only the END of each already-grouped scene to 1s after
   * its last confirmed kill. Simply shortening the raw individual ranges
   * changes which close fights merge, causing unexpected jump cuts.
   *
   * This changes no OCR, detection, kill ordering or Media3 export logic.
   */
  public static List<Range> planFinalVideo(List<Long> killsMs,
      List<Long> deathsMs,long lengthMs){
    List<Range> originalScenes=mergeOverlapping(
        calculateAvoidDeathsWithTail(killsMs,deathsMs,lengthMs,3000L));
    if(originalScenes.isEmpty())return originalScenes;
    List<Range> finalScenes=new ArrayList<>();
    for(Range scene:originalScenes){
      long lastKill=-1L;
      if(killsMs!=null)for(Long killAt:killsMs)
        if(killAt!=null && killAt>=scene.startMs && killAt<=scene.endMs)
          lastKill=Math.max(lastKill,killAt);
      // Preserve any V8.1 early cutoff that removed a subsequent death.
      long end=lastKill>=0L
          ? Math.min(scene.endMs,Math.min(lengthMs,lastKill+AFTER_KILL_MS))
          : scene.endMs;
      if(end>scene.startMs+350L)
        finalScenes.add(new Range(scene.startMs,end));
    }
    return finalScenes;
  }

}
