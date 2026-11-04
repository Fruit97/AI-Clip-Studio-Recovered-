# HOK Highlight AI V2 (Xiaomi Pad 6)

**APK V2 is an offline, on-device highlight editor.** It uses a visual HUD banner heuristic in addition to OCR, scanning a sampled frame **every 400 ms**. This no longer requires English text to produce *candidate* kill moments. The app then exports H.264 MP4 highlights from 3 seconds before to 3 seconds after each selected event, including audio, 720p and high target bitrate.

## What the detector can and cannot do
- **Visual search:** locate top-center kill banner overlays, which are similar in Thai and English interfaces. False positives and missed kills are still possible, especially with custom HUDs, small overlays, portrait changes, unusual aspect ratios or varying game versions.
- **Text search:** the bundled ML Kit recognizer is Latin-script/English OCR only; it **does not recognize Thai text**. See https://developers.google.com/ml-kit/vision/text-recognition/v2/languages
- **Own vs. teammate kill:** the HUD often shows both; visual-only marks are **unverified candidates** and must be reviewed. This is not a pretrained HOK neural model, and we do **not** guarantee that all or only player kills are selected. To fix false positives, use the checkbox beside each candidate, or add missing times manually.
- **Speed and battery:** frame scanning and OCR of 30–45 minute clips can be slow and warm up the tablet; leave the app open during processing.
- **FPS:** source frame rate is preserved by Media3. A 60 FPS source normally exports at 60 FPS; this version does not synthesize true new 60 FPS frames from 30 FPS footage.
- **Storage:** imports use Android document picker; no video uploading or root. 3 GB import size cap, 45-minute cap. Output uses local internal space and gallery MediaStore.

## Build
JDK 17; Gradle 8.13; Android Gradle Plugin 8.13.2; compile SDK 36.

`gradle -p hok-highlight-android testDebugUnitTest assembleDebug`

Workflow `.github/workflows/hok-highlight-apk.yml` uploads a debug-signed APK artifact and publishes a stable GitHub Release.

**Important upgrade note:** GitHub Actions' debug-signed APKs can be signed with different ephemeral keystores. If Android reports "app not installed" when upgrading V1 to V2, uninstall V1 first, then install V2. Keep the original videos safe in your gallery; uninstalling clears app-private output files.
