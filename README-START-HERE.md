# AI Clip Studio V14 — Universal Visual Matching

Source folder: `ai-clip-studio/`.

This is an **offline-tested source bundle**, NOT a deployed version. Existing Render site still runs V13.

Key difference: every narration beat must be matched to observed uploaded video footage using an AI-provided visual evidence and confidence score, for any topic or action. No hardcoded sea/animal keyword list.

Gemini scores are self-reported; accuracy cannot be guaranteed without running real Gemini and inspecting generated videos. The V12 related-shot reuse and approximate text-based narration timing limitations still remain.

Dockerfile path: `ai-clip-studio/Dockerfile`; context `.`.

Tests: cd ai-clip-studio && python -m pytest -q test_v14_semantic.py test_v11.py test_v12.py test_v13_safety.py
