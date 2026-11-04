package com.pad6.hokhighlight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Tracks only the PERSONAL sword (K) counter once the K/D/A HUD row is
 * independently locked from three stable three-number observations.
 *
 * After the row is located, targeted OCR of the sword digit can continue
 * following 0->1->2 even when ML Kit misses the skull or fist digits.
 * Unlocated numbers, unconfirmed fluctuations and decreases are never kills.
 */
public final class SwordCounterTracker {
  private KdaCounter.Observation location;
  private KdaCounter.Observation lockCandidate;
  private int lockSamples;
  private int totalFullReads;
  private int totalSwordReads;
  private int confirmedK=-1;
  private int pendingK=-1;
  private int pendingRepeats;
  private long firstPendingAt;
  private int ignoredNoise;

  public boolean hasLocation(){return location!=null;}
  public float swordX(){return location==null?-1f:location.x-.040f;}
  public float swordY(){return location==null?-1f:location.y;}
  public int confirmedKills(){return confirmedK;}
  public int fullReads(){return totalFullReads;}
  public int swordReads(){return totalSwordReads;}
  public int ignoredNoise(){return ignoredNoise;}

  public List<KdaCounter.Kill> feed(long atMs,
      KdaCounter.Observation full,int swordOnly) {
    if(atMs<0)return Collections.emptyList();
    if(full!=null) {
      totalFullReads++;
      if(location==null) {
        if(lockCandidate==null || !lockCandidate.sameLocation(full) ||
            !lockCandidate.sameValues(full)) {
          lockCandidate=full;
          lockSamples=1;
        } else {
          lockSamples++;
        }
        if(lockSamples>=3) {
          location=full;
          confirmedK=full.kills;
          pendingK=-1;
          pendingRepeats=0;
        }
      } else if(!location.sameLocation(full)) {
        // Do not replace a calibrated personal HUD with a scoreboard.
        ignoredNoise++;
        return Collections.emptyList();
      }
    }
    if(location==null)return Collections.emptyList();
    if(swordOnly>=0)totalSwordReads++;
    // Full HUD is preferred when both sources match. Conflicting OCR
    // estimates are not reliable enough to generate a highlight.
    if(full!=null && swordOnly>=0 && full.kills!=swordOnly) {
      ignoredNoise++;
      return Collections.emptyList();
    }
    int k=swordOnly>=0?swordOnly:full==null?-1:full.kills;
    if(k<0 || k>99)return Collections.emptyList();
    if(confirmedK>=0 && (k<confirmedK || k-confirmedK>5)) {
      ignoredNoise++;
      pendingK=-1; pendingRepeats=0;
      return Collections.emptyList();
    }
    if(k==confirmedK) {
      pendingK=-1;pendingRepeats=0;
      return Collections.emptyList();
    }
    if(pendingK!=k || atMs-firstPendingAt>12000L) {
      pendingK=k;pendingRepeats=1;firstPendingAt=atMs;
      return Collections.emptyList();
    }
    if(++pendingRepeats<3)return Collections.emptyList();

    int delta=k-confirmedK;
    if(delta<=0)return Collections.emptyList();
    confirmedK=k;
    pendingK=-1;pendingRepeats=0;
    List<KdaCounter.Kill> out=new ArrayList<>();
    // One increase may span multiple kills if the frame sampling missed
    // intermediate digits. Keep those events distinct but mark as inferred.
    long eventAt=Math.max(0L,firstPendingAt-200L);
    for(int i=0;i<delta;i++) {
      long event=Math.max(0L,eventAt-(delta-1-i)*330L);
      out.add(new KdaCounter.Kill(event,k-delta+i+1,delta>1,true));
    }
    return out;
  }
}
