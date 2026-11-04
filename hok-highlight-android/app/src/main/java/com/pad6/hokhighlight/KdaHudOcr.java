package com.pad6.hokhighlight;

import java.util.List;
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

    public static KdaCounter.Observation parse(List<Line> lines){
        if(lines==null)return null;
        KdaCounter.Observation best=null;
        double bestScore=Double.NEGATIVE_INFINITY;
        for(Line line:lines) {
            if(line==null||line.text==null)continue;
            // KDA expected in the upper-right HUD; avoid skill cooldowns and chat.
            if(line.x<.48f || line.x>.97f || line.y<0 || line.y>.15f)continue;
            Matcher match=TRIPLET.matcher(line.text);
            while(match.find()){
                int k=Integer.parseInt(match.group(1));
                int d=Integer.parseInt(match.group(2));
                int a=Integer.parseInt(match.group(3));
                if(k>45||d>45||a>60)continue;
                // Don't select team-score digits / left side or minimap rows.
                double score=-Math.abs(line.x-.755f)*2.0-
                              Math.abs(line.y-.065f)*2.0;
                if(score>bestScore){
                    bestScore=score;
                    best=new KdaCounter.Observation(k,d,a,line.x,line.y,true);
                }
            }
        }
        return best;
    }
}
