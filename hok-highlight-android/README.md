# HOK Highlight AI Pad6 V3 — Hero-only kill filter

Native Android app: choose a HOK gameplay recording (up to 3 GB, 45 minutes), scan every 400ms, review proposed kills, export 3 seconds before and after each selected kill. H.264 + AAC, 720p, high 16 Mbps target, source 60 FPS retained when available. Offline and no root required.

**V3 change: hero-only mode.** Stop including monster, jungle camp, lane minion, Tyrant, Overlord, Tempest Dragon and other neutral objective kills. Text filter checks objective tokens before "you have slain" or "defeated". Visual filter requires a two-sided hero portrait banner against the game-field background. A brief 1.2s lookahead allows later OCR text to veto a proposed kill that turns out to be a monster. This reduces accidental inclusion of monster footage.

Important limitations:
* **This is a heuristic, not an AI model trained on actual HOK screenshots.** There can still be missed hero kills and incorrect monster/teammate candidates in different HUD layouts or languages.
* ML Kit Latin OCR **cannot read Thai glyphs**. Thai mode relies on the visual two-portrait heuristic. Ambiguous results require reviewing the proposed timestamps before export. User needs to delete teammate kills if offered; automatic "my kills only" recognition is not yet proven.
* You need free internal storage for export; keep app foregrounded during scan/export. Videos are processed on device, not uploaded.
* No fake FPS interpolation. A 60fps original is expected to remain 60fps (hardware encoder can constrain actual result).
* Debug APK signed by GitHub runner. If install over V2 says incompatible certificate, uninstall V2 first (back up anything saved in app-private storage).

Build on Java 17: `gradle -p hok-highlight-android testDebugUnitTest assembleDebug`. Automation on branch hok-highlight-apk-v3 publishes an APK under GitHub Releases only after build and tests pass.
