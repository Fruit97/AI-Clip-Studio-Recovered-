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
      if (!out.isEmpty() && start <= out.get(out.size()-1).endMs + 250) {
        Range old = out.remove(out.size()-1);
        out.add(new Range(old.startMs, Math.max(old.endMs,end)));
      } else out.add(new Range(start,end));
    }
    return out;
  }
}
