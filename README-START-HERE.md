# AI Clip Studio V15 — Exactly One Minute (30 FPS)

V15 builds on the recovered V14 source. When selecting 60 seconds (the new UI default), it targets a script for one minute, checks voice tempo, and validates the exported MP4 has exactly 1,800 frames at 30 fps and a total duration of ~60.00 seconds (within 0.05 seconds of media container rounding). It does not fabricate footage. Longer clips and visually rich sources work best; clips shorter than 35 seconds are rejected for 60-second mode rather than looped blindly. Gemini quotas still apply. No extra Gemini request is made for duration adjustment.

Render: Docker, context '.', Dockerfile 'ai-clip-studio/Dockerfile', branch 'main'.

Automated restore ZIP filename: AIClipStudio_V15_OneMinute_FullSource.zip

Run tests locally: `cd ai-clip-studio && python -m pytest -q test_v11.py test_v12.py test_v13_safety.py test_v14_semantic.py test_v15_60seconds.py`

This package is a full source ZIP, not an APK. Successful local tests do not guarantee remote Gemini API availability, quota, or live server rendering performance.
