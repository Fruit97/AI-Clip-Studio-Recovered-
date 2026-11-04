package com.pad6.hokhighlight;

import java.util.List;
import java.util.ArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * STRICT recognition of a personal K / D / A readout.
 * A random group of three numeric HUD labels is NOT reliable evidence.
 * Screen position is only a plausibility check, not the sole classifier.
 */
public final class KdaHudOcr {
    private KdaHudOcr(){}
    private static final Pattern TRIPLET=Pattern.compile(
        "(?<![0-9])([0-9]{1,2})\\s*[/|\\u2044\\u2215]\\s*"+
        "([0-9]{1,2})\\s*[/|\\u2044\\u2215]\\s*([0-9]{1,2})(?![0-9])");

    public static final class Line {
        public final String text;
        public final float x,y;
        public Line(String text,float x,float y){
            this.text=text;this.x=x;this.y=y;
        }
    }

    private static int digit(String input){
        if(input==null)return -1;
        String t=input.trim();
        // ML Kit often reads the game's isolated white zero as Latin O.
        if(t.equalsIgnoreCase("o") || t.equals("〇") || t.equals("○"))t="0";
        if(t.equals("I") || t.equals("l"))t="1";
        return t.matches("[0-9]{1,2}")?Integer.parseInt(t):-1;
    }

    /** Numeric value from OCR of an isolated sword digit crop. */
    public static int parseSingle(String text){
        return digit(text);
    }

    /**
     * Once the three-column HUD was locked, read the sword column even if
     * the skull/fist values cannot be recognized in this particular frame.
     * The location must come from the previously calibrated full K/D/A row.
     */
    public static int parseSword(List<Line> lines,float swordX,float swordY){
        if(lines==null || swordX<0 || swordY<0)return -1;
        int found=-1;
        double best=Double.POSITIVE_INFINITY;
        for(Line line:lines){
            if(line==null)continue;
            int value=digit(line.text);
            if(value<0)continue;
            double dx=Math.abs(line.x-swordX), dy=Math.abs(line.y-swordY);
            if(dx>.032 || dy>.028)continue;
            double distance=dx*2.0+dy;
            if(distance<best){
                best=distance;
                found=value;
            }
        }
        return found;
    }

    public static KdaCounter.Observation parse(List<Line> lines){
        if(lines==null)return null;
        KdaCounter.Observation best=null;
        List<KdaCounter.NumberBox> looseDigits=new ArrayList<>();
        double bestScore=Double.NEGATIVE_INFINITY;
        for(Line line:lines) {
            if(line==null||line.text==null)continue;
            // KDA expected in the upper-right HUD; avoid skill cooldowns and chat.
            if(line.x<.45f || line.x>.98f || line.y<0 || line.y>.195f)continue;
            // In normal HOK matches the KDA may render as three separate
            // digits under small hero icons, WITHOUT / characters. V5 could
            // never read this UI. Treat those as provisional until the
            // temporal tracker calibrates the stable HUD location.
            String only=line.text.trim();
            int single=digit(only);
            if(single>=0){
                looseDigits.add(new KdaCounter.NumberBox(single,line.x,line.y));
            } else {
                // Some game versions render 0 0 0 as one OCR line.
                String[] parts=only.split("\\s+");
                if(parts.length==3){
                    int a=digit(parts[0]),b=digit(parts[1]),c=digit(parts[2]);
                    if(a>=0 && b>=0 && c>=0)
                        for(int n=0;n<3;n++)
                            looseDigits.add(new KdaCounter.NumberBox(
                                n==0?a:n==1?b:c,line.x+(n-1)*.04f,line.y));
                }
            }
            Matcher match=TRIPLET.matcher(line.text);
            while(match.find()){
                int k=Integer.parseInt(match.group(1));
                int d=Integer.parseInt(match.group(2));
                int a=Integer.parseInt(match.group(3));
                if(k>99||d>99||a>99)continue;
                // Don't select team-score digits / left side or minimap rows.
                double score=-Math.abs(line.x-.755f)*2.0-
                              Math.abs(line.y-.065f)*2.0;
                if(score>bestScore){
                    bestScore=score;
                    best=new KdaCounter.Observation(k,d,a,line.x,line.y,true);
                }
            }
        }
        if(best!=null) return best;
        KdaCounter.Observation provisional=KdaCounter.parse(looseDigits);
        return provisional;
    }
}
