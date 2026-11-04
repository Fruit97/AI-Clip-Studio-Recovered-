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
        VisualSignal(double score,double dark,double left,double right) {
            this.score=score; centerDark=dark; leftColor=left; rightColor=right;
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
            double score=.47*center.dark + .22*left.colorful +
                         .21*right.colorful + .10*contrast;
            // Avoid pure black loading screens, minimaps, and generic dark scenery.
            if(left.colorful+right.colorful<.28) score*=.45;
            if(center.dark<.43) score*=.6;
            if(score>best.score)
                best=new VisualSignal(score,center.dark,left.colorful,right.colorful);
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
    public static final class Tracker {
        private long lastEvent=-1000000;
        private boolean active;
        private int streak;
        private int absent;
        private Category previousCategory=Category.NONE;
        private String previousLabel="";
        private static final double VISUAL_THRESHOLD=.61;
        public Candidate feed(long atMs,VisualSignal vision,TextSignal text) {
            if(atMs<0 || vision==null || text==null)return null;
            if(text.category==Category.OTHER) {
                streak=0;
                return null;
            }
            boolean visible=vision.score>=VISUAL_THRESHOLD;
            if(visible) {streak++;absent=0;}
            else {streak=0;if(++absent>=2){active=false;previousCategory=Category.NONE;previousLabel="";}}
            boolean own=text.category==Category.OWN;
            boolean named=text.category==Category.MAYBE;
            boolean newNamed=named && (!text.label.equals(previousLabel) || previousCategory!=Category.MAYBE);
            boolean newOwn=own && (!active || previousCategory!=Category.OWN || !text.label.equals(previousLabel));
            boolean event=newOwn || (named && (visible || vision.score>.35) && newNamed)
                    || (visible && streak>=2 && !active);
            if(!event || atMs-lastEvent<MIN_GAP_MS) return null;
            lastEvent=atMs;active=true;
            previousCategory=text.category;previousLabel=text.label;
            if(own)return new Candidate(atMs,"OCR ระบุคิลของเรา: "+text.label,true);
            if(named)return new Candidate(atMs,"ข้อความคิล (ตรวจว่าเป็นคิลของเรา): "+text.label,true);
            return new Candidate(atMs,"ภาพแถบคิล (ต้องตรวจว่าเป็นคิลของเรา)",false);
        }
    }
}
