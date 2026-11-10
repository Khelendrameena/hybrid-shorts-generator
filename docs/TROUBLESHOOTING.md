# Troubleshooting

**Backend offline on Home page** — Start it: `run.bat`, or manually
`.venv\Scripts\activate` + `python -m uvicorn backend.main:app --port 8000`.
Check http://localhost:8000/api/health — it reports Laya/Ollama status and VRAM.

**Ollama offline / model missing** — Install Ollama (https://ollama.com/download),
then `ollama serve` and `ollama pull qwen3:4b`. Without Ollama the pipeline still
works: metadata falls back to deterministic transcript-derived titles (clips are
labelled `source: fallback` in the Editor so you can regenerate later).

**Laya not installed / load failed** — `pip install laya` (Python 3.10+; it pulls
torch + transformers, ~2 GB). First load downloads the 1.3 GB checkpoint from
Hugging Face. If `laya.load()` *hangs*, that's the documented TensorFlow-probe
deadlock — `run.bat` already sets `USE_TF=0`; set it yourself if you start the
backend manually. Until Laya loads, the engine honestly labels itself
`heuristic-fallback` on every clip (Analysis page) — scores then come only from
deterministic features. Nothing is faked either way.

**CUDA out of memory (RTX 3050 4 GB)** — The pipeline unloads models between
stages and sends Ollama `keep_alive=0`. If OOM still hits: set Whisper model to
`base` in Settings, close other GPU apps, and restart the backend. Every stage
also has a CPU fallback for Whisper/Laya.

**Whisper is slow on CPU** — A 1-hour video on CPU can take a long time. Use the
GPU build of ctranslate2 (installed by default with faster-whisper on Windows)
or pick a smaller Whisper model (`base`/`tiny`) in Settings for drafts.

**YouTube download fails** — Update yt-dlp: `pip install -U yt-dlp`. Private,
age-gated or region-locked videos cannot be downloaded; download the file
yourself (where permitted) and use Upload instead.

**"No audio stream" error** — The source has no audio track; there is nothing
to transcribe. Use a different source file.

**Subtitles missing in the rendered Short** — FFmpeg must be a build with
libass (the standard Gyan.FFmpeg Windows build includes it). The per-clip
`.ass`/`.srt` files are kept next to the render under the project folder
(`data/projects/<id>/renders/`) for inspection.

**Job stuck / server restarted mid-job** — Jobs are marked failed with a
"Resume" option on the Processing page. Resume skips checkpointed stages
(transcript, analysis, candidates, metadata) instead of redoing them.

**Frontend won't build** — Node 18+ required. Delete `frontend/node_modules`
and `frontend/.next`, then `npm install` again.

**Port already in use** — Something else holds 8000/3000/11434. Stop it, or
change the backend port and set `NEXT_PUBLIC_API_URL` for the frontend.
