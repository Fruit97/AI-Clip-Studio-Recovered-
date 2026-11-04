package com.pad6.hokhighlight;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class HighlightPlanner {
  private HighlightPlanner() {}
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
    List<Long> sorted = new ArrayList<>(killsMs);
    Collections.sort(sorted);
    List<Range> out = new ArrayList<>();
    for (Long when : sorted) {
      if (when == null || when < 0 || when > videoLengthMs) continue;
      long start = Math.max(0, when-3000);
      long end = Math.min(videoLengthMs,when+3000);
      if (end <= start) continue;
      // IMPORTANT: one kill must produce one clip, even if adjacent clips
      // overlap. V1-V4 merged two close kills into one and lost shot count.
      out.add(new Range(start,end));
    }
    return out;
  }
  /**
   * Keep the player's own death out of the rendered clip. The death timestamp
   * comes from a confirmed rise in D. Trim before the death rather than
   * leaving a death screen in the 3-second post-kill tail.
   */
  public static List<Range> calculateAvoidDeaths(
      List<Long> killsMs,List<Long> deathsMs,long videoLengthMs){
    List<Range> base=calculate(killsMs,videoLengthMs);
    if(deathsMs==null||deathsMs.isEmpty())return base;
    List<Range> out=new ArrayList<>();
    for(Range r:base){
      long a=r.startMs,b=r.endMs;
      for(Long when:deathsMs){
        if(when==null)continue;
        long cutoff=Math.max(0L,when-800L);
        if(cutoff>a && cutoff<b)b=cutoff;
      }
      if(b>a+350L)out.add(new Range(a,b));
    }
    return out;
  }

}
