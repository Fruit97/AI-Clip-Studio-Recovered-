# HOK Highlight AI V7.5 — sword-number-only trigger

Native Android highlight editor for Xiaomi Pad 6. Fully offline on-device processing; up to 3 GB, 45-minute source video. Preserves game audio and attempts 720p H.264/AAC at 16 Mbps target, maximum 60 FPS (no interpolation for input below 60 FPS). Cuts 5 seconds before and 3 seconds after each selected event, keeping consecutive kills separate.

## V7.5 sword-counter-only correction (November 4, 2026)
- The user's two reference images show sword = 0 (no own kills yet), then sword = 1 (one own hero kill). The skull and fist counters are D (own deaths) and A (assists). They must NOT trigger highlights.
- One automatic selection is made only when the player's calibrated sword K counter rises from a previous stable value, such as 0->1, 1->2, 2->3, etc. The event time comes from the first new K reading, not a banner.
- Generic hero-kill banners, portraits, deaths, monsters, objective announcements and teammate eliminations **never** authorize, cancel, or time a clip.
- Removed banner/OCR + visual scanning from the video processing loop, reducing extra work and the risk of monster-based false positives.
- Standalone temporary OCR values are not accepted; all three icon-column readings have to be stable and coherent. If OCR confidence is insufficient, mark is left unchecked, not auto-exported.
- Still exports up to 5 seconds before and 3 after each confirmed K increment; own-death footage is trimmed out.
- Added synthetic tests covering sword 0->1->2, no kills for D/A-only, no changes from banners, exact 5+3 second cuts. Actual Android OCR accuracy has not been measured with 24235.mp4.

## V7.4 cut-window change (November 4, 2026)
- Each confirmed increase in the player's own sword/K counter creates a 5-second pre-kill lead and a 3-second post-kill tail, up to 8 seconds per event.
- At the start/end of a source video, crop the window to existing footage (no filler or invented frames).
- The post-kill tail ends before a confirmed own death. If death is detected in the five-second lead, the clip stays out of auto-export instead of rendering a death/respawn scene.
- Separate close kills remain separate highlights under the prior requirement (their eight-second windows may overlap in the output).
- Existing boss/objective, monster, death and teammate exclusion rules continue unchanged.
- Regression tests cover 8-second clips, clip boundaries, consecutive kills and death trimming.
- Tests are synthetic; actual sample 24235.mp4 still has not been decoded end-to-end and real-world detection accuracy is not verified.

## V7.3 strict own-hero evidence (November 4, 2026)
- Generic Double/Triple/Penta Kill (including Thai labels) does not confirm a personal kill when K/D/A OCR is weak.
- An explicit own-hero elimination phrase can corroborate weak K/D/A, but an unverified banner alone never auto-exports.
- Objective text detected from the neutral-boss banner OCR is preserved as negative evidence and prevents selecting any K candidate within 1.8 seconds. Simultaneous real hero and objective kills may need manual review.
- Monster/objective banners are not even proposed for manual selection.
- Cancelled scans preserve both the old highlights and the old death timeline.
- Added regression tests covering generic multikills, objective-only, objective-adjacent, and own-hero cases.
- The user's 24235.mp4 could not be decoded by the current file-processing environment. These tests are synthetic; real-device OCR and rendered video accuracy are not verified.

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
