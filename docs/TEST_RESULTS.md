# Test results

Environment for automated runs: Linux build VM (no GPU), Python 3.12, FFmpeg 8.1,
Node 24. Target-machine-only stages (real GPU Whisper, live Ollama server) are
marked as such; everything else below was actually executed, not assumed.

## Unit / integration suite — `python -m pytest tests/ -q`

**24 passed** (scoring formula exactness, repetition penalty, dedup IoU +
containment, timestamp optimizer word-snapping + sentence extension, Laya
typed-answer parsers for `choice`/`score`/`noul`, heuristic-fallback scoring,
Ollama JSON extraction incl. `<think>` blocks and code fences, metadata
validation + fallback, subtitle ASS/SRT generation, YouTube URL validation,
FastAPI health/project/settings flow via TestClient).

## Synthetic end-to-end — `python scripts/e2e_synthetic.py`

Generated a 70s 1280×720 synthetic video (FFmpeg testsrc2 + tone) and ran the
real pipeline stages:

- ✅ ffprobe: valid, 1280×720, 25 fps, audio stream detected
- ✅ Scene detection (fallback path), 35 frames sampled, 71 audio-energy windows
- ✅ Candidate detection produced clips with scores/categories/reasons
  (engine honestly reported as `heuristic-fallback` on this machine because the
  `laya` package was not yet installed in the test venv — see Laya section)
- ✅ Metadata: with no Ollama server reachable, deterministic fallback produced
  valid metadata (`#shorts` present) and labelled itself `source: fallback`
- ✅ Render: output verified by ffprobe as **1080×1920, H.264, AAC** — a real Short

## Frontend — `npm run build`

✅ Next.js production build succeeds; all 6 routes compile:
`/`, `/processing`, `/analysis`, `/editor`, `/export`, `/settings`.

## Backend smoke

✅ `uvicorn backend.main:app` boots; `GET /api/health` returns Laya install
status, Ollama status and RAM usage; `GET /` returns app info.

## Laya live-model run

See the update appended below after the `laya` package + checkpoint were
installed on the test machine. The model card's own caveats apply: the
multilingual checkpoint ships uncalibrated and is near-chance zero-shot on
some workflow benchmarks — which is precisely why this project blends its
probabilities with deterministic features and records `engine` per clip.

## Not run on the build VM (run on the target Windows machine)

- Faster-Whisper with a real speech video (model download ≈0.5 GB + GPU) —
  code path is the standard `faster-whisper` API with word timestamps, CPU fallback included.
- Ollama `qwen3:4b` live generation — `ollama pull qwen3:4b`, start Ollama, then
  any clip's **Regenerate** button exercises it; offline behaviour is covered above.
- Spec §13 manual matrix (10-min / 30-min podcast / 1-hour interview / Hindi /
  English / multi-speaker) — use real videos on the target machine and the
  checklist in the README.
