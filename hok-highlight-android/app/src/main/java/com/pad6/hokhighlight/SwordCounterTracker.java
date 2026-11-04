package com.pad6.hokhighlight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Personal sword/K counter, independent of kill banners or objective notices.
 *
 * AUTO: a stable K/D/A row must be located before reading its sword digit.
 * PIN: a user can tap the NUMBER BESIDE the sword on a video frame if automatic
 * layout detection fails. This avoids guessing the HUD position from FPS,
 * team score or monster counters, while still requiring repeated OCR readings.
 */
public final class SwordCounterTracker {
  private KdaCounter.Observation location;
  private KdaCounter.Observation lockCandidate;
  private int lockSamples, totalFullReads, totalSwordReads, ignoredNoise;
  private long lastLockCandidateAt=-1L, firstPendingAt;
  private float pinnedX=-1f,pinnedY=-1f;
  private int confirmedK=-1,pendingK=-1,pendingRepeats;

  public void pinSword(float x,float y) {
    if(x<0f || x>1f || y<0f || y>1f)
      throw new IllegalArgumentException("invalid sword-number position");
    pinnedX=x;pinnedY=y;
    location=null;lockCandidate=null;lockSamples=0;
    confirmedK=-1;pendingK=-1;pendingRepeats=0;
  }
  public boolean isPinned(){return pinnedX>=0f;}
  public boolean hasLocation(){return isPinned() || location!=null;}
  public float swordX(){return isPinned()?pinnedX:
      location==null?-1f:location.swordX;}
  public float swordY(){return isPinned()?pinnedY:
      location==null?-1f:location.y;}
  public int confirmedKills(){return confirmedK;}
  public int fullReads(){return totalFullReads;}
  public int swordReads(){return totalSwordReads;}
  public int ignoredNoise(){return ignoredNoise;}

  public List<KdaCounter.Kill> feed(long atMs,
      KdaCounter.Observation full,int swordOnly) {
    if(atMs<0)return Collections.emptyList();
    if(full!=null)totalFullReads++;
    if(swordOnly>=0)totalSwordReads++;

    if(isPinned()) {
      // The user picked the precise NUMBER next to the sword.
      // A FULL HUD read can help only if its sword column is at this same
      // confirmed location; unrelated team-score numbers cannot override it.
      int k=swordOnly;
      if(k<0 && full!=null &&
          Math.abs(full.swordX-pinnedX)<.030f &&
          Math.abs(full.y-pinnedY)<.025f)
        k=full.kills;
      return track(atMs,k);
    }

    if(full!=null) {
      if(location==null) {
        // OCR may miss a full K/D/A frame between good observations. Allow
        // up to 15 s between readings of the same stationary HUD instead
        // of demanding three CONSECUTIVE video frames.
        if(lockCandidate==null || !lockCandidate.sameLocation(full) ||
            !lockCandidate.sameValues(full) ||
            atMs-lastLockCandidateAt>15000L) {
          lockCandidate=full;lockSamples=1;
        } else {
          lockSamples++;
        }
        lastLockCandidateAt=atMs;
        if(lockSamples>=3) {
          location=full;
          confirmedK=full.kills;
          pendingK=-1;pendingRepeats=0;
        }
      } else if(!location.sameLocation(full)) {
        ignoredNoise++;
        return Collections.emptyList();
      }
    }
    if(location==null)return Collections.emptyList();
    if(full!=null && swordOnly>=0 && full.kills!=swordOnly) {
      ignoredNoise++;
      pendingK=-1;pendingRepeats=0;
      return Collections.emptyList();
    }
    int candidate=swordOnly>=0?swordOnly:full==null?-1:full.kills;
    return track(atMs,candidate);
  }

  private List<KdaCounter.Kill> track(long atMs,int k) {
    if(k<0 || k>99)return Collections.emptyList();
    if(confirmedK>=0 && (k<confirmedK || k-confirmedK>5)) {
      ignoredNoise++;
      pendingK=-1;pendingRepeats=0;
      return Collections.emptyList();
    }
    if(k==confirmedK) {
      pendingK=-1;pendingRepeats=0;
      return Collections.emptyList();
    }
    if(pendingK!=k || atMs-firstPendingAt>7000L) {
      pendingK=k;pendingRepeats=1;firstPendingAt=atMs;
      return Collections.emptyList();
    }
    if(++pendingRepeats<3)return Collections.emptyList();

    // For pinned mode, the first stable value defines the BASELINE, not a
    // kill. We cannot invent a kill when the video starts already at K=3.
    if(confirmedK<0) {
      confirmedK=k;
      pendingK=-1;pendingRepeats=0;
      return Collections.emptyList();
    }

    int delta=k-confirmedK;
    confirmedK=k;
    pendingK=-1;pendingRepeats=0;
    if(delta<=0)return Collections.emptyList();

    List<KdaCounter.Kill> out=new ArrayList<>();
    long eventAt=Math.max(0L,firstPendingAt-200L);
    for(int i=0;i<delta;i++) {
      long at=Math.max(0L,eventAt-(delta-1-i)*330L);
      // If OCR jumped 0 -> 2, the TWO EXACT KILL TIMES are unknown.
      // Report both for manual review, but do NOT auto-export guessed clips.
      out.add(new KdaCounter.Kill(at,k-delta+i+1,delta>1,delta==1));
    }
    return out;
  }
}
