# HOK Highlight AI V8.2 — five seconds before, one second after

Native Android highlight editor for Xiaomi Pad 6. Fully offline on-device processing; up to 3 GB, 45-minute source video. Preserves game audio and attempts 720p H.264/AAC at 16 Mbps target, maximum 60 FPS (no interpolation for input below 60 FPS). Cuts 5 seconds before and 1 second after each verified kill; overlapping windows merge without repeating video frames.

## V8.2: final 5+1-second cut timing (November 4, 2026)
- User-approved setting: five seconds **before** the confirmed personal sword/K increment and exactly one second **after** it. An isolated kill creates a six-second source segment, bounded by the available video.
- Example: kill at 01:20 => crop 01:15 to 01:21. Close consecutive kills merge into a continuous fight without rewinding; separated fight scenes jump cut to the next clip.
- Retains automatic scan/import, automatic one-file MP4 concatenation, game audio, 720p resolution, 60 FPS ceiling, and the separate death-screen exclusion logic.
- Regression tests were updated for the 5+1 window, adjacent kills, separated cuts, source boundaries and death trimming.
- Building the APK and passing unit tests do not prove complete K OCR accuracy or on-device video rendering.

## V8.1: make confirmed highlights into the final video (November 4, 2026)
- After selecting a HOK MP4, the app starts detection automatically; the scan and export buttons remain available for manual retry or rescans.
- When the sword/K reader verifies one or more personal kills, the app automatically invokes Media3 Transformer and assembles all selected source ranges into a SINGLE MP4 without requiring a separate export button.
- Each kill uses a 5s pre-roll and 3s post-roll, adjusted before detected own deaths and source video boundaries. Overlapping/touching ranges are merged so short consecutive multi-kill fights do not rewind the same footage. Separate fights jump directly to the next highlight (hard cut).
- The app records the output to Movies/HOK Highlights in Android MediaStore and offers a playback button to open the resulting MP4.
- JUnit regression tests check consecutive overlapping kills, separated fights, no kill/death-only rejection, and death trimming.
- This change addresses the handoff from detection to final-video export; it does NOT by itself improve the underlying visual OCR reliability. Real HOK clip 24242.mp4 and on-device video rendering have not been tested end-to-end in this runtime.

## V8.0: revised detection strategy (November 4, 2026)
- V7.6 scanned only 82/694 frames with a complete K/D/A OCR group; V7.7 still required three consecutive full K/D/A snapshots before it knew where to look. In intermittent OCR this condition is rarely met.
- AUTO MODE: three matching full K/D/A observations can lock the HUD **across missing frames** (bounded by a 15-second gap), not necessarily consecutive samples. The actual sword column x is recorded from the first OCR digit instead of guessing center minus 0.04.
- ONE-TAP FALLBACK: a real frame is retrieved using Android MediaMetadataRetriever and the top-right HUD strip is displayed enlarged, independently of the VideoView player, which may initially appear black. User taps the NUMBER next to the sword icon to lock a stable normalized video coordinate. This does not require rooting or network/API keys.
- With the sword column pinned or auto-located, the app OCRs the focused K digit on each sampled frame, and checks the full K/D/A row periodically to recognize own deaths. The focused crop is enlarged 5× with a high-contrast retry for white digits.
- K must increase and remain stable for three readings. 0->1 and 1->2 give one automatically selected shot per increment. D/A changes alone, monsters, objectives and team kill banners do not create auto shots.
- OCR jumps such as 0->2 without intermediate timestamps are **review-only**, since the exact two kill times cannot be reliably derived; the app will no longer silently invent times.
- The exported shot remains at 5 s BEFORE the K change and 3 s AFTER, with a trim before recognized own deaths; source boundary clamping stays unchanged.
- Automated JUnit tests cover pinned sword 0->1->...->10, falsely read digits, intermittent full-HUD frames, K jumps, death/assist changes, and highlight timing.
- Important: actual sample 24242.mp4 was provided but the current container-backed video runtime errored. GitHub build/unit tests cannot substitute for running the OCR and MP4 exporter on the user's actual Xiaomi Pad 6, and no perfect-accuracy claim is made.

## V7.7 partial OCR recovery (November 4, 2026)
- The screenshot of V7.6 shows only 82 of 694 frames yielded a parseable three-column HUD, so requiring all three numbers each time can miss real K increases.
- A new SwordCounterTracker first calibrates the personal sword/skull/fist row using three agreeing full observations; only then can targeted sword-only reads confirm a K increase.
- When full-row OCR does not report the K digit, the app tries an enlarged focused crop at the locked sword-number position. Repeated skull/fist OCR is not required just to detect a sword update.
- Three agreeing sword readings are required before a new highlight is selected. Single-frame errors, decreasing values, huge jumps, and contradictory full vs focused OCR are discarded.
- The old full K/D/A tracker is kept for own-death timing; nothing from monster, objective or teammate banners triggers a highlight.
- Added synthetic unit tests covering K=0 through K=10 while skull/fist OCR is missing, no false cuts from D/A increases, OCR blips, and conflict rejection.
- This runtime cannot decode the user's 24242.mp4 due to container tool errors. The APK build test does not prove on-device video accuracy.

## V7.6 continuous K-counter reliability fixes (November 4, 2026)
- User screenshot confirms V7.5 scan finished without finding a verified K even though sword/K is visible in the gameplay.
- Removed the overly strict hard-coded x/y anchor which failed when HUD shifts with screen ratio, capture crop or game UI layout. Three evenly spaced and repeated sword/skull/fist digit values may now calibrate within the upper HUD band, and the counter's location must remain stable for the new reading.
- Source frames are now decoded for OCR up to 1920x1080 instead of 1280x720 to preserve the small K digits. OCR crop includes 27% of the top of the frame instead of 20%.
- ML Kit sometimes reads the isolated digit 0 as O or ○; normalize such OCR output for numeric HUD parsing.
- Keep scanning counter increments 0->1->2->3->...->10, regardless of total kills, while D/A-only increases never make a cut. Fixed detection is still heuristic and depends on OCR reading the actual numeric HUD.
- Report the number of frames where K/D/A OCR was parsed, so an empty result can be diagnosed rather than incorrectly claiming zero kills.
- The 5-second pre-kill + 3-second post-kill rule remains unchanged. The actual source footage on Xiaomi Pad 6 is not yet validated end-to-end.

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
