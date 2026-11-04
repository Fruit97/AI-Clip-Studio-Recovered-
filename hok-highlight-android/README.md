# HOK Highlight AI V6 — Kill-only (not player deaths)

Native offline Android highlight editor for Honor of Kings and Xiaomi Pad 6.

## Main goals
- Upload from on-device storage (MP4/MOV up to 3 GB, 45 minutes, no video internet upload).
- Detect **your enemy-hero eliminations only**, and **never automatically select a player's death**, teammate kills, minions, monsters or bosses.
- One 6-second highlight for each qualifying personal kill (3s before + 3s after), with overlapping kills kept as separate clips.
- Output 720p H.264 high target 16Mbps + AAC game audio. Original 60fps can be preserved if supported by device encoder. No synthetic 60fps from 30fps source.

## V5 bug and V6 correction
V5 selected a loose triplet of OCR numbers in the top HUD; this can be a team score, clock or other numeric information. Misreading "Deaths" as "Kills" could create footage of the user's own death. OCR could also miss kill moments.

V6 now:
- Tries to identify personal K/D/A as an evenly spaced, stable 3-counter group at the upper HUD; requires **three consistent reads of all K, D and A**, and stable region coordinates.
- **Only automatically selects** when personal K increases while D does not. A death-only increase is ignored. If both K and D increase in one unobservable interval, mark the timing as ambiguous **unchecked** rather than auto-export a death.
- Visual HUD kill-banner recognition is only a source of *unverified* candidates, deselected by default. It no longer auto-triggers clips from monster or enemy kills. Visual banner retiming can only be used if OCR explicitly says "YOU have slain..." and is close to the KDA increment.
- For two kills close together, create **two** clips; the planned segments are **not merged**. No fixed kill count (8, 10, etc.).
- Status shows last observed K/D/A, number of death-only events excluded and ambiguous events needing review.

## Limitations
- The KDA OCR is heuristic and needs a HUD layout it can reliably read. Without a known ground-truth dataset of the actual player HUD and a successfully decoded test video, automatic detection accuracy is **not validated**.
- HUD cropping could still target the wrong numbers or fail if the HUD differs from the images we researched. If personal KDA cannot be calibrated, visual kill proposals remain **unchecked** and manual review is required.
- A simultaneous true kill and own death is ambiguous and deselected automatically; the user can review that case if desired. This conservative behavior favors no unintended death highlights over perfect recall.
- The video sample 24218.mp4 was present as a prior upload but could not be decoded in the current runtime, so no timing/kill claims have been made from that source.
- All analysis and rendering occurs on the Android device: battery/CPU use can be substantial for large videos. Keep the app foregrounded.

## Build / release
Java 17; Gradle 8.13; Android Gradle Plugin 8.13.2; SDK 36.

`gradle -p hok-highlight-android clean testDebugUnitTest assembleDebug`

After CI tests pass, GitHub Actions publishes the debug-signed APK to Releases. GitHub runner signing certificates can change between versions: if updating over V5 fails, uninstall it first, after backing up any files saved in app-private storage.
