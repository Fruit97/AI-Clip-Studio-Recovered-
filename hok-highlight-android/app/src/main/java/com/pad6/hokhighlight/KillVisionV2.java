package com.pad6.hokhighlight;

import java.util.Locale;

/**
 * Lightweight, on-device HOK HUD event proposer.
 * This is an OCR + visual heuristic, NOT an ML model trained on HOK gameplay.
 * Visual-only results MUST be reviewed: ally/enemy banners look similar.
 */
public final class KillVisionV2 {
    private KillVisionV2() {}
    public static final int SAMPLE_INTERVAL_MS = 400;
    public static final int MIN_GAP_MS = 1800;

    public enum Category { OWN, MAYBE, OTHER, NONE }

    public static final class TextSignal {
        public final Category category;
        public final String label;
        TextSignal(Category c, String l) { category=c; label=l; }
    }

    public static TextSignal parseText(String original) {
        if (original == null) return new TextSignal(Category.NONE, "");
        String text=original.toLowerCase(Locale.ROOT)
          .replace("\n"," ").replaceAll("\\s+"," ").trim();
        if (text.isEmpty()) return new TextSignal(Category.NONE,"");
        // Boss/minion text is NEVER an eligible hero kill, even when OCR also sees "slain".
        String objective=HeroOnlyGuard.objectiveWord(text);
        if(objective!=null) return new TextSignal(Category.OTHER,"monster/objective: "+objective);
        // Negatives MUST be checked first, to avoid confusing death/ally messages with kills.
        String[] negative = {
          "you have been slain", "you were slain", "you have been defeated",
          "you are defeated", "an ally has been defeated", "an ally has been slain",
          "enemy double kill", "enemy triple kill", "enemy quadra kill",
          "enemy penta kill", "enemy legendary", "enemy godlike",
          "victory", "destroyed a tower", "tower destroyed",
          "ป้อม", "คุณถูกสังหาร", "คุณถูกกำจัด", "ถูกสังหาร", "พ่ายแพ้"
        };
        for (String s:negative) if (text.contains(s)) return new TextSignal(Category.OTHER,s);
        String[] own = {
          "you have slain", "you've slain", "you have defeated",
          "you defeated", "you have killed", "you killed",
          "คุณสังหาร", "คุณกำจัด", "คุณได้สังหาร"
        };
        for (String s:own) if (text.contains(s)) return new TextSignal(Category.OWN,s);
        String[] maybe = {
          "first blood", "double kill", "doublekill", "triple kill", "triplekill", "quadra kill", "quadrakill",
          "quad kill", "penta kill", "pentakill", "godlike", "legendary",
          "unstoppable", "dominating", "killing spree", "mega kill",
          "defeated", "defeat", "slain", "สังหาร", "กำจัด", "ฆ่าสอง", "ฆ่าสาม",
          "ฆ่าสี่", "ฆ่าห้า", "ดับเบิลคิล", "ทริปเปิลคิล"
        };
        for (String s:maybe) if (text.contains(s)) return new TextSignal(Category.MAYBE,s);
        return new TextSignal(Category.NONE,"");
    }

    public static final class VisualSignal {
        public final double score;
        public final double centerDark;
        public final double leftColor;
        public final double rightColor;
        public final double heroPair;
        VisualSignal(double score,double dark,double left,double right) {
            this(score,dark,left,right,Math.sqrt(Math.max(0,left)*Math.max(0,right)));
        }
        VisualSignal(double score,double dark,double left,double right,double pair) {
            this.score=score; centerDark=dark; leftColor=left; rightColor=right;
            this.heroPair=pair;
        }
    }

    static double clamp(double x) {return Math.min(1.0,Math.max(0.0,x));}

    static final class Patch {
        double luminosity;
        double dark;
        double colorful;
        Patch(double lum,double dark,double color){luminosity=lum;this.dark=dark;colorful=color;}
    }

    static Patch patch(int[] argb,int width,int height,
                  double x0,double x1,double y0,double y1) {
        int left=(int)(width*x0),right=(int)(width*x1);
        int top=(int)(height*y0),bottom=(int)(height*y1);
        left=Math.max(0,Math.min(width-1,left));
        right=Math.max(left+1,Math.min(width,right));
        top=Math.max(0,Math.min(height-1,top));
        bottom=Math.max(top+1,Math.min(height,bottom));
        double sumLum=0, darkness=0, color=0;
        int count=0;
        int stepX=Math.max(1,(right-left)/32);
        int stepY=Math.max(1,(bottom-top)/14);
        for(int y=top;y<bottom;y+=stepY) for(int x=left;x<right;x+=stepX) {
            int p=argb[y*width+x];
            int r=(p>>16)&255,g=(p>>8)&255,b=p&255;
            double lum=(r*54.0+g*183.0+b*19.0)/256.0;
            int max=Math.max(r,Math.max(g,b));
            int min=Math.min(r,Math.min(g,b));
            sumLum+=lum;
            if(lum<116)darkness++;
            if(max-min>48 && max>110)color++;
            count++;
        }
        return new Patch(sumLum/Math.max(count,1),darkness/Math.max(count,1),color/Math.max(count,1));
    }

    /**
     * Tests multiple top-center banner rows to cope with different HUD positions.
     * Returns candidates, not a verified player kill.
     * Bitmap pixels must be ARGB and 16:9-ish landscape screenshots.
     */
    public static VisualSignal analyze(int[] argb,int width,int height) {
        if(argb==null || width<80 || height<50 || argb.length<width*height)
            return new VisualSignal(0,0,0,0);
        VisualSignal best=new VisualSignal(0,0,0,0);
        // HOK often renders a dark kill strip with hero portraits on both sides.
        for(double cy:new double[]{0.135,0.185,0.235,0.285}) {
            Patch center=patch(argb,width,height,.35,.65,cy-.033,cy+.033);
            Patch left=patch(argb,width,height,.205,.315,cy-.052,cy+.052);
            Patch right=patch(argb,width,height,.685,.795,cy-.052,cy+.052);
            Patch below=patch(argb,width,height,.37,.63,cy+.082,cy+.132);
            double contrast=clamp((below.luminosity-center.luminosity+5.0)/65.0);
            double pair=HeroOnlyGuard.portraitPairEvidence(left.colorful,right.colorful,
                    center.dark,contrast);
            double score=.47*center.dark + .22*left.colorful +
                         .21*right.colorful + .10*contrast;
            // Hero eliminations usually contain TWO circular hero portraits.
            // A jungle monster/dragon objective can have a single large icon.
            if(left.colorful<.12 || right.colorful<.12) score*=.34;
            if(pair<.21) score*=.55;
            if(center.dark<.43) score*=.6;
            if(score>best.score)
                best=new VisualSignal(score,center.dark,left.colorful,right.colorful,pair);
        }
        return best;
    }

    public static final class Candidate {
        public final long timestampMs;
        public final String reason;
        public final boolean textConfirmed;
        Candidate(long at,String reason,boolean confirmed) {
            timestampMs=at;this.reason=reason;textConfirmed=confirmed;
        }
    }

    /**
     * Temporal rising-edge detector suppresses repeats of the same banner.
     * OCR own-kill phrases are stronger than image-only cues.
     */
    /**
     * Hero-only temporal gate: two-portrait banner, OCR label, and a short
     * lookahead window allowing later "Tyrant/Overlord" OCR to veto a false hit.
     * Visual-only cues are still *unverified*, not proof of the user's own kill.
     */
    public static final class Tracker {
        private static final long LOOKAHEAD_MS=1200;
        private static final long OBJECTIVE_COOLDOWN_MS=1800;
        private long lastCommitted=-1000000L;
        private long blockedUntil=-1000000L;
        private int visualStreak=0;
        private int missingStreak=0;
        private boolean active=false;
        private String priorWord="";
        private Category priorCategory=Category.NONE;
        private Candidate pending;
        private long pendingTime;

        public Candidate feed(long atMs,VisualSignal vision,TextSignal text) {
            if(atMs<0||vision==null||text==null)return null;
            if(text.category==Category.OTHER) {
                // Death, ally death or neutral objective: do not clip this.
                pending=null; visualStreak=0; active=false;
                blockedUntil=Math.max(blockedUntil,atMs+OBJECTIVE_COOLDOWN_MS);
                priorWord="";priorCategory=Category.NONE;
                return null;
            }
            if(atMs<blockedUntil) return null;
            Candidate ready=null;
            if(pending!=null && atMs-pendingTime>=LOOKAHEAD_MS) {
                ready=pending;
                pending=null;
                lastCommitted=ready.timestampMs;
            }
            boolean paired=HeroOnlyGuard.isHeroPortraitPair(vision);
            boolean strip=paired && vision.score>=.60;
            if(strip) {visualStreak++;missingStreak=0;}
            else if(++missingStreak>=2) {
                visualStreak=0;active=false;priorWord="";priorCategory=Category.NONE;
            }
            boolean own=text.category==Category.OWN;
            boolean named=text.category==Category.MAYBE;
            boolean newNamed=named && (!text.label.equals(priorWord)||priorCategory!=Category.MAYBE);
            boolean newOwn=own && (!active||priorCategory!=Category.OWN||!text.label.equals(priorWord));
            boolean markOwn=own && newOwn;
            boolean markNamed=named && paired && strip && newNamed;
            boolean markVisual=strip && visualStreak>=2 && !active && vision.heroPair>=.27;
            boolean isNew=markOwn || markNamed || markVisual;
            if(isNew && pending==null && atMs-lastCommitted>=MIN_GAP_MS) {
                active=true;
                priorCategory=text.category;priorWord=text.label;
                String note=markOwn ? "ตรวจพบคิลของเราในข้อความ (เช็กเป้าหมาย): "+text.label :
                    markNamed ? "แถบคิลฮีโร่ + ข้อความ (ตรวจคิลของเรา): "+text.label :
                    "แถบคิลฮีโร่สองฝั่ง (ต้องยืนยันว่าเราฆ่า ไม่ใช่เพื่อน)";
                pending=new Candidate(atMs,note,markOwn);
                pendingTime=atMs;
            }
            return ready;
        }

        public Candidate finish(long atMs) {
            if(pending==null || atMs-pendingTime<LOOKAHEAD_MS)return null;
            Candidate result=pending;pending=null;
            return result;
        }
    }
}
