# HOK Highlight AI — Android APK (Xiaomi Pad 6)

Native, on-device Honor of Kings highlight editor. Import a 1–3 GB video using Android's file picker without uploading to a server; scan sampled frames with bundled ML Kit OCR (best results for *English* kill banners); inspect and edit candidate kill timestamps; stitch segments from 3 seconds before to 3 seconds after each kill; export an H.264/AAC MP4 scaled to 720p and copy to the Movies/HOK Highlights gallery folder.

**Important limits:** This is OCR-assisted candidate detection, not a trained HOK kill-classification model. Thai kill notifications or some HOK HUD variants can be missed; add missing kills manually at the video seek position. The app does not guarantee that every detected banner is your own kill. Verify candidate markers before exporting. Video frame rate is retained from the source; 60 FPS is produced when source is 60 FPS, without fake interpolation. The encoder requests a 16 Mbps bitrate but device encoders may use a different bitrate. Large files require significant *free internal storage* and the user should keep the app in foreground during scanning/rendering.

## Build
In the project root, use Android Gradle Plugin 8.7.3 with Gradle 8.10.2 and JDK 17:
`gradle assembleDebug testDebugUnitTest`

GitHub Actions workflow: `.github/workflows/hok-highlight-apk.yml`. The signed debug APK is uploaded as a workflow artifact named `HOK-Highlight-AI-APK`. For private use; debug-signed builds are NOT suitable for Play Store release.

No root, no Internet permission, no ACCESS_ALL_FILES permission needed. Media selection uses Storage Access Framework and outputs use MediaStore.
