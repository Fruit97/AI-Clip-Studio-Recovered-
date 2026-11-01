FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-thai-tlwg fontconfig ca-certificates && fc-cache -f && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY ai-clip-studio/ /app/
RUN pip install --no-cache-dir -r requirements.txt && python -m py_compile app.py editorial_v9.py v11.py v12.py v13_safety.py v14_semantic.py v15_60seconds.py v17_quality.py v18_voice.py v20_proxy.py v21_storyflow.py v22_scene.py v23_retry.py v24_minute_knowledge.py v25_adaptive.py v26_multishot.py v27_replan.py v28_alignment.py v29_verified_selection.py v30_source_first.py v30_render_reliability.py v31_illustrative.py v32_recovery.py v33_recovery.py v34_visual_refusal.py
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
