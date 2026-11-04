package com.pad6.hokhighlight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * Reads an individual's K/D/A numeric triplet from the live HUD.
 * Only a change of the player's K (not team score, minion or objective events)
 * can certify an elimination. UI visibility/layout varies by video.
 */
public final class KdaCounter {
    private KdaCounter() {}

    public static final class NumberBox {
        public final int value;
        public final float x,y;
        public NumberBox(int value,float x,float y) {
            this.value=value;this.x=x;this.y=y;
        }
    }
    public static final class Observation {
        public final int kills,deaths,assists;
        public final float x,y;
        public Observation(int kills,int deaths,int assists,float x,float y) {
            this.kills=kills;this.deaths=deaths;this.assists=assists;
            this.x=x;this.y=y;
        }
    }

    /**
     * KDA is a horizontal trio of small counters on the upper right.
     * Reject clocks, FPS, the two-number team scoreboard and large gaps.
     * Coordinates are normalized to the original frame dimensions.
     */
    public static Observation parse(List<NumberBox> raw) {
        if(raw==null||raw.size()<3)return null;
        List<NumberBox> digits=new ArrayList<>();
        for(NumberBox b:raw) {
            if(b.value>=0 && b.value<=60 && b.x>=.48f && b.x<=.98f &&
               b.y>=0 && b.y<.155f)digits.add(b);
        }
        digits.sort(Comparator.comparingDouble(n->n.x));
        Observation best=null;
        double bestScore=-1e9;
        for(int i=0;i<digits.size();i++){
            NumberBox a=digits.get(i);
            for(int j=i+1;j<digits.size();j++){
                NumberBox b=digits.get(j);
                float dx1=b.x-a.x;
                if(dx1<.012f||dx1>.105f)continue;
                for(int k=j+1;k<digits.size();k++){
                    NumberBox c=digits.get(k);
                    float dx2=c.x-b.x;
                    if(dx2<.012f||dx2>.105f)continue;
                    if(Math.abs(a.y-b.y)>.022f||Math.abs(b.y-c.y)>.022f)continue;
                    float span=c.x-a.x;
                    if(span<.055f||span>.195f)continue;
                    double ratio=Math.max(dx1,dx2)/Math.min(dx1,dx2);
                    if(ratio>2.5)continue;
                    // Right-most suitable 3-digit group beats the team K/A score.
                    double score=c.x*10-Math.abs(dx1-dx2)*9+
                                 ((a.value<30&&b.value<30&&c.value<40)?.12:0);
                    if(score>bestScore){
                        bestScore=score;
                        best=new Observation(a.value,b.value,c.value,(a.x+c.x)/2,(a.y+b.y+c.y)/3);
                    }
                }
            }
        }
        return best;
    }

    public static final class Kill {
        public final long atMs;
        public final int individualTotal;
        public final boolean inferred;
        Kill(long at,int total,boolean inferred) {
            this.atMs=at;this.individualTotal=total;this.inferred=inferred;
        }
    }

    /**
     * Two identical consecutive OCR readings are required to confirm each
     * player-kill counter increase. Separate events are emitted per increment:
     * 8 verified kills => 8 events; doubles within 1 second are not deduped.
     */
    public static final class Tracker {
        private Observation baseline;
        private Observation pending;
        private long pendingAt;
        private int stable=0;
        private int samples=0;
        private int trustedSnapshots=0;

        public boolean isCalibrated(){return baseline!=null;}
        public int trustedSnapshots(){return trustedSnapshots;}
        public int individualKills(){return baseline==null?-1:baseline.kills;}
        public int samples(){return samples;}

        public List<Kill> feed(long atMs,Observation observed){
            samples++;
            if(observed==null)return Collections.emptyList();
            if(pending!=null && (Math.abs(pending.x-observed.x)>.045f ||
                  Math.abs(pending.y-observed.y)>.025f || pending.kills!=observed.kills)) {
                pending=null;stable=0;
            }
            if(baseline!=null &&
               (Math.abs(baseline.x-observed.x)>.05f ||
                Math.abs(baseline.y-observed.y)>.035f))
                return Collections.emptyList();
            if(baseline!=null && (observed.kills<baseline.kills ||
                  observed.kills-baseline.kills>5 ||
                  observed.deaths+2<baseline.deaths ||
                  observed.assists+2<baseline.assists)) {
                pending=null;stable=0;
                return Collections.emptyList();
            }
            if(pending==null) {pending=observed;pendingAt=atMs;stable=1;}
            else stable++;
            if(stable<2)return Collections.emptyList();
            trustedSnapshots++;
            if(baseline==null){
                baseline=observed;
                pending=null;stable=0;
                return Collections.emptyList();
            }
            if(observed.kills<=baseline.kills){
                baseline=observed;pending=null;stable=0;
                return Collections.emptyList();
            }
            int delta=observed.kills-baseline.kills;
            List<Kill> out=new ArrayList<>();
            // The first observed increased KDA counter appears *after* the kill.
            // When multiple kills occur between samples, preserve each count.
            for(int i=0;i<delta;i++){
                long t=Math.max(0,pendingAt-250L-(delta-1-i)*250L);
                out.add(new Kill(t,baseline.kills+i+1,delta>1));
            }
            baseline=observed;pending=null;stable=0;
            return out;
        }
    }
}
