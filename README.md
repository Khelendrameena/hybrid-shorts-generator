# 🎬 Hybrid AI YouTube Shorts Generator

Turn long YouTube videos and local MP4/MOV/MKV files into multiple high-quality
**1080×1920 YouTube Shorts** — automatically, **100% locally, with zero paid APIs**.

Two AI models with strictly separate jobs:

| Model | Role | What it actually is |
|---|---|---|
| **A — LAYA** (`convaiinnovations/laya-multilingual`) | **Decision intelligence**: finds, scores and ranks the best moments | A 322M-param **non-generative decision model** (mmBERT-base + decision head). It takes text + *typed questions* (`choice` / `score` / `noul`) and returns probabilities in one forward pass. It never writes text and **never sees video frames** — see below. |
| **B — OLLAMA** (`qwen3:4b`, changeable in Settings) | **Creative generation**: titles, hooks, descriptions, hashtags, thumbnail text | A local generative LLM served by Ollama. It only receives clips Laya already selected. **It cannot change timestamps or scores.** |

Plus **Faster-Whisper** (transcription, word timestamps, Hindi/English/Hinglish),
**OpenCV + PySceneDetect** (scenes, faces, frames), and **FFmpeg** (rendering).

> 📄 **Read [`docs/LAYA_RESEARCH.md`](docs/LAYA_RESEARCH.md) before judging the design.**
> Laya is *not* a chatbot-style LLM. This project implements its real typed-question
> interface, documents its limits (ships uncalibrated, text-only, weak `score`
> primitive), and blends its probabilities 60/40 with deterministic transcript/visual
> features — exactly because the model card itself tells you to calibrate before trusting it.

---

## Quick start (Windows 11)

**Prerequisites:** Python 3.10+, [FFmpeg](https://ffmpeg.org) (`winget install Gyan.FFmpeg`),
[Ollama](https://ollama.com/download), Node.js 18+.

```bat
setup.bat   :: venv + pip install + ollama pull qwen3:4b + npm install
run.bat     :: starts Ollama (if needed) + backend :8000 + frontend :3000
```

Then open **http://localhost:3000**, paste a YouTube URL or upload a video, and watch
the Processing page. Approve clips in the Editor, render, and download the ZIP from Export.

Linux/macOS: create the venv, `pip install -r requirements.txt`, `ollama pull qwen3:4b`,
`cd frontend && npm install`, then `./run.sh`.

**First processing run downloads** (one time, cached): Laya-multilingual ≈1.3 GB from
Hugging Face, Faster-Whisper `small` ≈0.5 GB. No accounts, no API keys, no Gemini/Groq/OpenAI anywhere.

## How it works

```
YouTube URL / local file
  → yt-dlp / upload  → ffprobe metadata check
  → Faster-Whisper transcription (word + segment timestamps, JSON + SRT saved)
  → Video understanding: scenes (PySceneDetect), frames (1/2s + around cuts),
    face tracking (OpenCV), per-second audio energy, black-frame flags
  → Candidate windows: overlapping, sentence-bounded, grown from every segment
    start (never fixed intervals)
  → LAYA scores every candidate with typed questions (hook? emotion level?
    category? informative? standalone? complete? clear?) → component scores
  → Weighted final score (spec formula) − repetition penalty → dedup (IoU +
    containment) → timestamp optimization on word boundaries + padding
  → OLLAMA writes validated JSON metadata (3 retries → deterministic fallback)
  → Editor: review scores/reasons, adjust cut, edit titles, approve/reject
  → FFmpeg render: face-aware 9:16 crop, animated word-highlight subtitles
    (4 themes), loudnorm, H.264 + AAC → individual MP4s or one Export ZIP
```

**Scoring formula** (configurable in `config/default.yaml`):

```
Final = 0.20·Hook + 0.15·Emotion + 0.15·Info + 0.15·Standalone + 0.15·Story
      + 0.10·Clarity + 0.10·Visual − RepetitionPenalty      (clamped 0–100)
```

Scores estimate engagement potential — nobody can guarantee virality, and this app doesn't claim to.

**Clip rules:** min 15s · preferred ≤ 60s · max 180s · padding 0.4s/0.6s — all configurable.

## Built for an RTX 3050 (4 GB VRAM) + 16 GB RAM

- Only **one heavy model is resident at a time** (`backend/models/manager.py`):
  Whisper → unload → Laya → unload → Ollama (sent `keep_alive=0`). CPU fallback at every stage.
- Real sizes: Laya ≈0.65 GB fp16 · Whisper-small ≈1 GB · qwen3:4b ≈2.5 GB Q4 — each fits alone; together they would not.
- Transcripts, video analysis, candidates and metadata are **checkpointed per stage** —
  restart the server mid-job and hit **Resume**; finished stages are skipped.
- RAM/VRAM usage is shown on the Home page (`/api/health`).

## Dashboard

| Page | What you do there |
|---|---|
| **Home** | Paste YouTube URL / upload video, model health chips, recent projects |
| **Processing** | Live stage progress (download → whisper → analysis → Laya → Ollama → render), cancel, resume |
| **AI Analysis** | Full transcript, highlight timeline, per-clip score breakdown + Laya's reasons |
| **Shorts Editor** | Preview data, change timestamps, edit subtitles metadata/titles, regenerate via Ollama, approve/reject |
| **Export** | Download single Shorts, all-as-ZIP, SRTs, metadata JSON |
| **Settings** | Laya model id, Ollama URL/model, Whisper size, max clips, min score, durations, subtitle theme, language |

## Project structure

```
backend/   FastAPI — api/, models/ (laya_engine, ollama_engine, manager),
           transcription/ (faster-whisper), video/ (yt-dlp, ffprobe, scenes,
           frames, faces), analysis/ (candidates, features, scoring,
           timestamps, dedup), generation/ (metadata + JSON validation),
           rendering/ (ffmpeg + ASS subtitle engine), jobs/ (pipeline,
           progress, recovery), storage/ (SQLite + project manager)
frontend/  Next.js 14 + Tailwind — app/ pages, components/, hooks/, services/
tests/     pytest suite (24 tests)     scripts/e2e_synthetic.py  full offline E2E
config/    default.yaml                docs/LAYA_RESEARCH.md     docs/TROUBLESHOOTING.md
```

## Testing

```bash
pip install pytest
python -m pytest tests/ -q            # 25 unit/integration tests
python scripts/e2e_synthetic.py       # builds a synthetic video and runs the
                                      # whole pipeline incl. a real 1080×1920 render
```

**Verified live (2026-11-10):** the real `laya` package (0.4.30) + the real
multilingual checkpoint were run through this engine on Hindi and English
samples — see `docs/TEST_RESULTS.md` for the raw typed answers, including a
live contradiction between Laya's `noul` and `choice` answers that the
calibration blend is designed to absorb.

Manual test matrix (spec §13): 10-min video · 30-min podcast · 1-hour interview ·
Hindi video · English video · multi-speaker video. Verify timestamps, clip
boundaries, subtitle integrity, no black frames, no duplicates, 9:16 output,
valid JSON metadata, and resume-after-interruption (kill the backend mid-job,
restart, Resume — checkpoints skip finished stages).

## Honest limitations

- **Laya is text-only and ships uncalibrated** (its own model card says so). Visual
  suitability comes from OpenCV/audio features, never from Laya. The 60/40 blend and
  the labelled heuristic fallback (used only when `laya` isn't installed/loadable)
  exist for this reason. Fine-tuning Laya on labelled Shorts data is the upgrade path.
- **Speaker diarization** is not built into Faster-Whisper; the transcript carries a
  clearly-labelled pause-based *speaker-turn hint*, not true diarization.
- **OCR** is an optional hook (install `easyocr`); without it the pipeline simply skips OCR.
- YouTube downloads use yt-dlp — only download content you have the right to use.

## License

MIT for this project's code. Laya weights/package: Apache-2.0 (Convai Innovations).
Whisper, yt-dlp, FFmpeg and Ollama models carry their own licenses.
