# HOK Highlight AI V5 — Player-owned hero kill detection

This app is an experimental offline HOK highlight editor built specifically for Android/Xiaomi Pad 6. It imports videos up to 3 GB, 45 minutes, scans at 400ms for banners and about 1.2s for the personal KDA counter. Output: one MP4 segment per player hero kill, from 3s before to 3s after each kill, in H.264/AAC at 720p with 16Mbps target bitrate. It keeps source framerate (60fps input for 60fps output).

## Why V1–V4 failed
1. The old visual HUD detector could mistake a monster/boss notification for a hero elimination, especially with Thai interface.
2. Cooldown suppressed closely spaced multi-kills; highlight planner also merged overlapping kills.
3. Hard coded RGB/portrait thresholds in V3 missed all kills, and V4 remained a generic banner detector.

## V5 approach
- OCR **individual player K/D/A HUD** at the top of the game screen. Only a confirmed increase in the player's personal kill stat K yields automatically selected moments; jungle monsters/creeps/neutral objectives do not increment individual player hero kills. Two consecutive compatible OCR observations are required. Each delta becomes one individual mark: if the count rises by 2, create 2 marks.
- Visual kill banners refine candidate timestamps; they no longer by themselves certify a personal hero kill.
- If the individual K/D/A cannot be read, generic visual detections are shown **unchecked** for user review. This prevents accidental automatic exporting of monster clips. Use the existing manual mark controls if needed.
- Remove merging of nearby cuts: close kills stay as separate 6s segments, even when content overlaps.
- No fixed expected number of kills: 8 kills => 8 marks, 10 => 10, subject to OCR successfully reading an accurate personal KDA. Testing includes counts 8, 10, overlapping timestamps, OCR fluctuation, monster-only events.

**Known limitations**
- This is not a trained/HOK-validated neural detector; reading small HUD numbers can fail depending on game language, layout, UI hiding or video resolution. An OCR reading from a spectator HUD or team score that mimics a three-number KDA can be incorrect; review marks before export. Some clips may have no readable personal KDA.
- We were not able to run V5 against the user's original uploaded gameplay video in the active sandbox. Build and synthetic tests are **not** proof of real-game accuracy.
- Clip generation of overlapping segments duplicates action intentionally to preserve 1 clip per kill.
- Rendering and scanning use device CPU, memory and storage, must remain in foreground. No network upload.

Build: Android SDK 36, AGP 8.13.2, Gradle 8.13, JDK 17. `gradle -p hok-highlight-android testDebugUnitTest assembleDebug`.

Release APK is a GitHub Actions debug-signed build. If an old APK is signed with a different ephemeral key, uninstall it before installing V5 (after backing up app-private files).
