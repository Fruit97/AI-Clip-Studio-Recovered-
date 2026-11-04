package com.pad6.hokhighlight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * Player K/D/A tracker for the in-game HUD.
 * A valid kill is an increase in the player's K only, NOT D, A, total team
 * score, a death notification, or a monster/neutral objective banner.
 *
 * Numeral OCR is not by itself proof that a group is the personal KDA; the
 * user still needs to verify its HUD placement on real game footage.
 */
public final class KdaCounter {
    private KdaCounter() {}
    public static final class NumberBox {
        public final int value;
        public final float x,y;
        public NumberBox(int value,float x,float y){
            this.value=value;this.x=x;this.y=y;
        }
    }
    public static final class Observation {
        public final int kills,deaths,assists;
        public final float x,y;
        public final boolean trusted;
        public Observation(int kills,int deaths,int assists,float x,float y){
            this(kills,deaths,assists,x,y,true);
        }
        public Observation(int kills,int deaths,int assists,float x,float y,boolean trusted){
            this.kills=kills;this.deaths=deaths;this.assists=assists;
            this.x=x;this.y=y;this.trusted=trusted;
        }
        public boolean sameValues(Observation other){
            return other!=null && kills==other.kills &&
                   deaths==other.deaths && assists==other.assists;
        }
        public boolean sameLocation(Observation other){
            return other!=null && Math.abs(x-other.x)<.028f &&
                    Math.abs(y-other.y)<.016f;
        }
    }

    /**
     * Find 3 adjacent small counters in the upper-HUD K/D/A band.
     * Do not pick arbitrary "rightmost 3 numbers" (V5 bug):
     * game clock, gold and team scores are nearby.
     *
     * This layout prior may fail when a user customizes HUD; such scans
     * must remain unverified and cannot be silently treated as kills.
     */
    public static Observation parse(List<NumberBox> raw){
        if(raw==null||raw.size()<3)return null;
        List<NumberBox> numbers=new ArrayList<>();
        for(NumberBox n:raw){
            if(n.value>=0 && n.value<=45 && n.x>=.46f && n.x<=.86f &&
               n.y>=.012f && n.y<=.115f)numbers.add(n);
        }
        numbers.sort(Comparator.comparingDouble(n->n.x));
        Observation best=null;
        double bestScore=Double.NEGATIVE_INFINITY;
        for(int i=0;i<numbers.size();i++){
            NumberBox a=numbers.get(i);
            for(int j=i+1;j<numbers.size();j++){
                NumberBox b=numbers.get(j);
                double d1=b.x-a.x;
                if(d1<.018||d1>.090)continue;
                for(int k=j+1;k<numbers.size();k++){
                    NumberBox c=numbers.get(k);
                    double d2=c.x-b.x;
                    if(d2<.018||d2>.090)continue;
                    if(Math.abs(a.y-b.y)>.012f||Math.abs(c.y-b.y)>.012f)continue;
                    if(Math.max(d1,d2)/Math.min(d1,d2)>1.8)continue;
                    double centerX=(a.x+c.x)/2.0;
                    double centerY=(a.y+b.y+c.y)/3.0;
                    if(centerX<.54||centerX>.82||centerY>.11)continue;
                    // KDA typically near top-middle-right, scoreboard towards
                    // the centre and clock/minimap at the edges.
                    double score=-(Math.abs(centerX-.67)*2.5 +
                         Math.abs(centerY-.055)*3.0 +
                         Math.abs(d1-d2)*10.0);
                    if(score>bestScore){
                        bestScore=score;
                        best=new Observation(a.value,b.value,c.value,
                                (float)centerX,(float)centerY,false);
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
        Kill(long time,int total,boolean inferred){
            this.atMs=time;this.individualTotal=total;this.inferred=inferred;
        }
    }

    public static final class Tracker {
        private Observation baseline, pending;
        private long pendingAt, lastValidAt=-1L;
        private int stable, samples, trustedSnapshots, deathsIgnored, ambiguous;
        private int maxObservedKills=-1;
        private int rejectedUntrusted=0;
        private final List<Long> deathMoments=new ArrayList<>();
        private final List<Kill> ambiguousCandidates=new ArrayList<>();

        public boolean isCalibrated(){return baseline!=null;}
        public int individualKills(){return baseline==null?-1:baseline.kills;}
        public int individualDeaths(){return baseline==null?-1:baseline.deaths;}
        public int individualAssists(){return baseline==null?-1:baseline.assists;}
        public int maxObservedKills(){return maxObservedKills;}
        public int trustedSnapshots(){return trustedSnapshots;}
        public int samples(){return samples;}
        public int deathsIgnored(){return deathsIgnored;}
        public int ambiguousEvents(){return ambiguous;}
        public int rejectedUntrusted(){return rejectedUntrusted;}
        public List<Long> deathMoments(){return new ArrayList<>(deathMoments);}
        public List<Kill> drainAmbiguous(){
            List<Kill> copy=new ArrayList<>(ambiguousCandidates);
            ambiguousCandidates.clear();
            return copy;
        }

        /**
         * Requires 3 consistent OCR readings (K, D AND A). A D-only increase
         * must never produce a kill. If K and D rise together in the same
         * unobserved interval, the situation is ambiguous: reject auto-cut.
         */
        public List<Kill> feed(long atMs,Observation observed){
            samples++;
            if(atMs<0||observed==null)return Collections.emptyList();
            // Separate HUD numbers (without slash) are provisional.
            // Calibrate their location over 5 consistent reads; an arbitrary
            // one-off group of digits must never create a kill.
            if(!observed.trusted && baseline!=null && baseline.trusted) {
                rejectedUntrusted++;
                return Collections.emptyList();
            }
            if(baseline!=null && !baseline.sameLocation(observed)){
                // If KDA is occluded, don't accidentally track nearby team score.
                pending=null;stable=0;
                return Collections.emptyList();
            }
            if(baseline!=null &&
               (observed.kills<baseline.kills ||
                observed.deaths<baseline.deaths ||
                observed.assists<baseline.assists ||
                observed.kills-baseline.kills>5 ||
                observed.deaths-baseline.deaths>3 ||
                observed.assists-baseline.assists>9)){
                pending=null;stable=0;
                return Collections.emptyList();
            }
            if(pending==null || !pending.sameLocation(observed) ||
               !pending.sameValues(observed)){
                pending=observed;pendingAt=atMs;stable=1;
                return Collections.emptyList();
            }
            stable++;
            int required=(baseline==null && !observed.trusted)?5:3;
            if(stable<required)return Collections.emptyList();
            trustedSnapshots++;
            lastValidAt=atMs;
            pending=null;stable=0;

            if(baseline==null){
                baseline=observed;
                maxObservedKills=observed.kills;
                return Collections.emptyList();
            }
            int deltaK=observed.kills-baseline.kills;
            int deltaD=observed.deaths-baseline.deaths;
            int deltaA=observed.assists-baseline.assists;
            maxObservedKills=Math.max(maxObservedKills,observed.kills);
            baseline=observed;

            if(deltaD>0) {
                deathsIgnored+=deltaD;
                deathMoments.add(pendingAt);
            }
            // A death without a K increase cannot be a hero elimination.
            if(deltaK<=0)return Collections.emptyList();
            // If K and D rise in the same uncertain OCR interval, we cannot
            // guarantee a death-free highlight. Report ambiguity, not a cut.
            if(deltaD>0){
                ambiguous+=deltaK;
                for(int i=0;i<deltaK;i++)
                    ambiguousCandidates.add(new Kill(
                         Math.max(0L,pendingAt-500L-(deltaK-1-i)*330L),
                         observed.kills-deltaK+i+1,deltaK>1));
                return Collections.emptyList();
            }
            // If assists rose by an implausible amount and K changes too,
            // HUD probably shifted or the triplet was a team-score group.
            if(deltaA>5){
                ambiguous+=deltaK;
                for(int i=0;i<deltaK;i++)
                    ambiguousCandidates.add(new Kill(
                         Math.max(0L,pendingAt-500L-(deltaK-1-i)*330L),
                         observed.kills-deltaK+i+1,deltaK>1));
                return Collections.emptyList();
            }

            List<Kill> out=new ArrayList<>();
            long eventMs=Math.max(0L,pendingAt-500L);
            for(int i=0;i<deltaK;i++){
                long at=Math.max(0L,eventMs-(deltaK-1-i)*330L);
                out.add(new Kill(at,observed.kills-deltaK+i+1,deltaK>1));
            }
            return out;
        }
    }
}
