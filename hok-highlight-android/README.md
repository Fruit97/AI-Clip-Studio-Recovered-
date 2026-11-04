# HOK Highlight AI V4 — fix V3's zero-kill regression

This on-device Android editor runs offline on Xiaomi Pad 6. Imports MP4/MOV videos under 3 GB and 45 minutes, runs frame analysis every 400 milliseconds, and creates 3s-before / 3s-after highlight segments, preserving source audio. Media3 exports H.264/AAC 720p using a 16 Mbps requested bitrate; 60 FPS is retained when source is 60 FPS (hardware encoders can constrain actual output).

## Why V3 found 0 kills
V3's added heuristic required a two-portrait RGB contrast score exceeding a hard threshold. On real HOK UI colors it can be below that threshold, and the OCR recognizer bundled in the APK cannot read Thai script. Together this could discard all the original V2 candidate events.

## V4 behavior
- Restore **the original V2 banner image detector and threshold**, not the strict two-portrait filter.
- Preserve 400ms sampling and English ML Kit OCR.
- Delay proposing a candidate by 1.2 seconds to allow **explicit** OCR text that identifies a neutral monster (Tyrant, Overlord, Tempest Dragon, minion, creep, etc.) to veto the banner. Don't automatically reject unrecognized/Thai text.
- Clearly mark visual-only candidates as **unverified**; neither own-hero kills nor exclusion of every monster is guaranteed, as no real HOK model has been trained. Review before export; manually delete non-hero candidates or add missed hero kills.
- Avoid generic substrings ("lord", "ป่า") that could accidentally refer to a real enemy hero.

**Tests** cover the V2 visual regression, objective veto, real hero-kill OCR, repeated banner dedup, end-to-end Android APK build. These are synthetic unit tests, **not validation against actual HOK game recordings**. V4 is a fix for false negatives; distinguishing monsters in Thai HUDs without OCR is still unsolved.

JDK17 / Gradle 8.13 / AGP 8.13.2. Build: `gradle -p hok-highlight-android testDebugUnitTest assembleDebug`. GitHub Actions builds and publishes versioned APK automatically after tests pass.

Debug-signed APK may need uninstall of previous versions before install. Back up files stored in app-private storage first.
