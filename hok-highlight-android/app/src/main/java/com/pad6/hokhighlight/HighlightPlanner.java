package com.pad6.hokhighlight;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class HighlightPlanner {
  private HighlightPlanner() {}
  // One confirmed hero elimination: 5 seconds of approach and 3 seconds
  // of aftermath, clipped to the source recording boundaries.
  public static final long BEFORE_KILL_MS = 5000L;
  public static final long AFTER_KILL_MS = 3000L;
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
    if (videoLengthMs <= 0) return Collections.emptyList();
    List<Long> sorted = new ArrayList<>();
    if(killsMs!=null) for(Long value:killsMs)
      if(value!=null) sorted.add(value);
    Collections.sort(sorted);
    List<Range> out = new ArrayList<>();
    for (Long when : sorted) {
      if (when == null || when < 0 || when > videoLengthMs) continue;
      long start = Math.max(0, when-BEFORE_KILL_MS);
      long end = Math.min(videoLengthMs,when+AFTER_KILL_MS);
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
    if(killsMs==null || killsMs.isEmpty() || videoLengthMs<=0)
      return Collections.emptyList();
    if(deathsMs==null || deathsMs.isEmpty())
      return calculate(killsMs,videoLengthMs);
    List<Long> ordered=new ArrayList<>();
    for(Long value:killsMs)
      if(value!=null && value>=0 && value<=videoLengthMs)ordered.add(value);
    Collections.sort(ordered);
    List<Range> out=new ArrayList<>();
    for(Long killAt:ordered){
      long start=Math.max(0L,killAt-BEFORE_KILL_MS);
      long end=Math.min(videoLengthMs,killAt+AFTER_KILL_MS);
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

}
