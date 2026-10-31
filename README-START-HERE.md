# AI Clip Studio V17 — Quota-Safe One-Minute Editor

Source code: `ai-clip-studio/` with Dockerfile at `ai-clip-studio/Dockerfile` (context `.`).

V17 improvements, October 31 2026:
- Fixes observed VOICE failure: Gemini TTS produced 78.7 s for a requested 60 s edit. The existing WAV is adjusted locally with FFmpeg pitch-preserving atempo to 60 s, within bounded reasonable speed, rather than paying for another TTS request. Never cuts off words deliberately.
- Reduces 60-second script prompt target to ~445–535 Thai characters; trims overlong narratives by *whole visually grounded beats* before paid TTS and refuses insufficient footage/script *before* paid TTS.
- Preserves both raw Gemini analysis (`analysis-raw-v17.json`) and validated analysis in job checkpoints; if local validation fails, resume does not repeat a previously completed analysis request.
- No automatic Gemini 429, timeout or HTTP 5xx retries (quota-conscious). No extra model calls for duration correction.
- Retains V14 semantic video-to-narration shot matching, V16 short-segment render fix, 720x1280 30fps 1800-frame output, and original-audio/subtitle behavior.
- Includes offline regression tests and an end-to-end simulated Gemini -> local FFmpeg one-minute MP4 test.

Test commands (local Docker-style dependencies need FFmpeg/fonts installed):
```
cd ai-clip-studio
python -m pip install -r requirements.txt pytest
python -m pytest -q -m 'not slow'
python -m pytest -q test_v12.py::test_renders_original_media_with_repetition
python -m pytest -q test_v17_end_to_end_mocked.py
```

Gemini API was intentionally NOT contacted during testing. Actual model speech duration varies; voice clips outside the supported 46–85 seconds are rejected rather than sped up unnaturally or cut off. Render Free local checkpoints may disappear when the service restarts or is redeployed. The user should avoid redeploying with an active job. There is no guarantee of 100% success for all inputs.
