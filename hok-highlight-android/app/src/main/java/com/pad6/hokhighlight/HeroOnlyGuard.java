package com.pad6.hokhighlight;

import java.util.Locale;

/**
 * Conservative hero-elimination gate.
 *
 * Most HOK neutral objectives (Tyrant, Overlord, Tempest Dragon, minions,
 * jungle camps) do NOT constitute a player-vs-hero elimination.
 * This is a deterministic filter and must not be represented as a trained model.
 */
public final class HeroOnlyGuard {
    private HeroOnlyGuard() {}

    private static final String[] OBJECTIVES={
      // Bosses and map objectives in global HOK
      "tyrant", "overlord", "tempest dragon", "storm dragon",
      "dragon", "dark slayer", "abyssal", "lord", "vanguard",
      "spirit sentinel", "river sprite", "jungle camp", "jungle creep",
      "wild monster", "neutral monster", "jungle monster",
      "minion", "minions", "creep", "creeps", "monster", "monsters",
      "red buff", "blue buff", "crimson golem", "azure golem",
      "golem", "buff monster", "dragon pit",
      // Thai HUD terms when text is supplied from any supported recognition source
      "มอนสเตอร์", "มอนส์เตอร์", "มังกร", "ครีป", "ป่า", "บอส",
      "ไทแรนท์", "ไทแรนต์", "โอเวอร์ลอร์ด", "ออเวอร์ลอร์ด",
      "ราชามังกร", "มังกรพายุ", "ทรราช", "ทหารเลน", "สัตว์ป่า",
      // Chinese terms; these will need compatible OCR to be detected
      "暴君", "主宰", "风暴龙王", "野怪", "小兵"
    };

    public static String objectiveWord(String original) {
        if(original==null||original.isEmpty()) return null;
        String lower=original.toLowerCase(Locale.ROOT).replaceAll("\\s+"," ");
        for(String token:OBJECTIVES) {
            if(lower.contains(token))return token;
        }
        return null;
    }

    static double portraitPairEvidence(double left,double right,
                                       double centerDark,double contrast) {
        if(left<=0 || right<=0 || centerDark<.40)return 0;
        // Both side portraits must contain colorful details. A solo neutral
        // objective icon normally lacks one of those two portrait regions.
        double pair=Math.sqrt(Math.max(0,left)*Math.max(0,right));
        return Math.min(1,pair * (0.85 + 0.15*Math.max(0,Math.min(1,contrast))));
    }

    public static boolean isHeroPortraitPair(KillVisionV2.VisualSignal v) {
        return v!=null && v.centerDark>=.43 && v.leftColor>=.12
            && v.rightColor>=.12 && v.heroPair>=.21;
    }
}
