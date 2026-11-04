# HOK Highlight AI V7.2 — own-hero kills with evidence gating

Native Android highlight editor for Xiaomi Pad 6. Fully offline on-device processing; up to 3 GB, 45-minute source video. Preserves game audio and attempts 720p H.264/AAC at 16 Mbps target, maximum 60 FPS (no interpolation for input below 60 FPS). Cuts 3 seconds before and 3 seconds after each selected event, keeping consecutive kills separate.

## V7.2 real-sample HUD correction (November 4, 2026)
- Inspected real frames from `24218.mp4` at 1536x960 (277 seconds). Visible K progression goes from 0 to 1 to 2 to 3, with D rising once.
- The personal K/D/A digits under sword/skull/fist icons are at approximate normalized x centers .829/.867/.905, not the old .60/.67/.74.
- Updated OCR grouping to the real upper-right personal HUD band. A repeated and calibrated stable group there may now confirm K increases without relying on Latin OCR of Thai announcements.
- Added repeatable tests for 3 kills, 1 death, and team-score exclusions.
- Added a 60 FPS maximum to Media3 export. Lower-FPS input remains lower FPS; no synthetic interpolation.
- This is a frame-informed detector correction, not a claim of measured end-to-end Android OCR accuracy or a tested MP4 render on Xiaomi Pad 6.

## V7.1 fixes (November 4, 2026)
- Keep confirmed personal K-counter kills occurring shortly before the player's death; export trims subsequent death footage.
- Ignore enemy/ally multikill text and generic First Blood as supporting evidence for a weak HUD read.
- Cancelling a scan preserves the previous marker list rather than replacing it with incomplete scan results.
- UI labels and regression tests updated for this release.
- Actual gameplay footage has NOT been used for model calibration yet; measured game accuracy is unknown.

## V7 detector change
The old model was only heuristic color/shape pattern matching. It could take monster/dragon/objective kills and player death/teammate kill banners as if they were your kills. V6 also treated weak OCR groups of three HUD numbers as verified personal KDA, causing false positives.

V7 retains V6's KDA reader but makes a strict distinction:
- A **confirmed personal K/D/A readout** (a delimited triplet read repeatedly in the same place) can automatically select a K-only increase, provided a death is not nearby.
- A **provisional KDA reading** from three separate on-screen digits is *not* enough to select. It requires independent text evidence associated with hero-versus-hero kills (e.g. double kill, triple kill, "you have slain an enemy hero").
- Shape-only banners, monster/boss/dragon text, team score changes, own deaths (D-only increase), and generic "defeat" announcements are not automatically selected.
- Uncertain moments remain listed **unchecked** so they cannot contaminate the export. This means a real kill may require review if the HUD OCR is poor. This is a safety-vs-recall limitation, not a guarantee of 100% detection.
- KDA sampled every 400ms; consecutive kills remain separate segments (no merge). The event count varies with the recording; never hard coded to nine or any other number.

## Verification
Synthetic JUnit tests include no-hit monsters, dragon/overlord, deaths, own hero kills, multi-kills, 8/10/20 arbitrary kill counts, weak numeric OCR, overlapped shot boundaries. GitHub Actions builds the debug-signed APK if tests pass.

**Not yet verified on a decoded HOK gameplay video**. The user's prior sample 24218.mp4 has been located but runtime video decoding tools are not functioning in this session; do not claim actual accuracy.

To build: JDK 17, Gradle 8.13, AGP 8.13.2, Android SDK 36:
`gradle -p hok-highlight-android clean testDebugUnitTest assembleDebug`

Release APK uses a temporary GitHub Actions debug signing key. Upgrading directly from a prior version may fail; back up any app-private files and uninstall previous version first.
