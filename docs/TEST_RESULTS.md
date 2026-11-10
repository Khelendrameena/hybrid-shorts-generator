# Test results

Environment for automated runs: Linux build VM (no GPU), Python 3.12, FFmpeg 8.1,
Node 24. Target-machine-only stages (real GPU Whisper, live Ollama server) are
marked as such; everything else below was actually executed, not assumed.

## Unit / integration suite — `python -m pytest tests/ -q`

**25 passed** (scoring formula exactness, repetition penalty, dedup IoU +
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

## Laya live-model run — ✅ VERIFIED with the real checkpoint (2026-11-10)

`laya 0.4.30` + CPU torch were installed in the test venv and
`convaiinnovations/laya-multilingual` was downloaded from Hugging Face
(~1.5 GB cache). Running `LayaEngine.score_candidate()` (the exact code the
pipeline uses) on Hindi and English texts:

- Load from cache: **18.5 s**, `engine="laya"`, no errors.
- All **8 typed questions answered** in one predict. Real raw output (Hindi
  sample): `hook` noul **0.789**, `category` choice **"surprising" (0.381)**,
  `emotion_level` score **0.9615** with index-keyed probabilities
  `{"0":0.187,"1":0.671,"2":0.137,"3":0.006}` + legend — the parser was updated
  for this exact real format and a regression test now pins it.
- **Live proof of the calibration caveat:** on the same Hindi clip, `hook`
  (noul) said P(strong hook)=**0.79** while the A/B cross-check `hook_ab`
  chose **"B" (no) at 0.79** — flatly contradicting each other, exactly the
  over-confidence the model card warns about. The engine averages the two
  checks and blends 60/40 with deterministic features instead of trusting
  either number (resulting blended hook score: 42.1). This is why the blend exists.
- Full synthetic E2E re-run **with real Laya**: candidates produced with
  `engine="laya"`, top clip score **63.9**, category `surprising`, render
  again verified **1080×1920 H.264 + AAC**. ✅

Note: the first-ever load on this VM took ~10 min because two test processes
contended for the same HF cache lock over a slow filtered proxy, and the
hf-xet download path stalled once; `HF_HUB_DISABLE_XET=1` + a warm cache made
loads fast and reliable. On a normal home connection the one-time ~1.3 GB
download is unremarkable.

## Laya live-model run (verified 2026-11-10, build VM, CPU)

`laya` 0.4.30 + `convaiinnovations/laya-multilingual` (322M) installed in the
test venv; first load downloaded the checkpoint (~1.5 GB cache) in ~5:49 and
`laya.load(...)` returned a working agent. Two transcript windows were scored
through the project's own `LayaEngine.score_candidate`:

- Hindi/Hinglish hook text → engine `laya`, category `surprising` (P=0.38, diffuse:
  funny 0.21, neutral 0.17, educational 0.13), component scores 33–56
  (hook 42.1, emotion 33.4, info 38.7, standalone 37.3, story 56.2, clarity 55.1).
- English text → engine `laya`, category `surprising`, scores 32–53.

Real answer shapes confirmed (and now covered by `test_score_expected_real_laya_format`):
`noul` → `{"noul": 0.79, ...}`; `choice` → `{"choice": "B", "probabilities": {"A": 0.21, "B": 0.79}}`;
`score` → `{"score": 0.9615, "legend": {"0": "low", ...}, "probabilities": {"0": 0.19, "1": 0.67, ...}}`
— probability keys are **index strings**, and `score` is the 0-based expected
level index. A parser bug this run caught (subtracting 1 from the expected
index, under-scoring high-emotion windows by ~33 pts) is fixed in
`backend/models/laya_engine.py`.

Two honest observations from the live run, not bugs:
- **Hook signals disagreed**: `hook` noul said strong hook (0.79) while the
  A/B `choice` cross-check said no-hook (B, 0.79). The engine averages the two,
  which is the documented hedge — but treat hook scores as the noisiest component.
- **Scores cluster low**: the Hindi window's weighted final score is ~42, below
  the default `min_clip_score` of 55. Laya's Hindi probabilities are diffuse
  (nothing above 0.79, category max 0.38), so on the first real-video run on the
  target machine, check how many clips clear 55 — lowering it to ~40 or
  recalibrating the blend may be needed. Do not raise the threshold.

## Not run on the build VM (run on the target Windows machine)

- Faster-Whisper with a real speech video (model download ≈0.5 GB + GPU) —
  code path is the standard `faster-whisper` API with word timestamps, CPU fallback included.
- Ollama `qwen3:4b` live generation — `ollama pull qwen3:4b`, start Ollama, then
  any clip's **Regenerate** button exercises it; offline behaviour is covered above.
- Spec §13 manual matrix (10-min / 30-min podcast / 1-hour interview / Hindi /
  English / multi-speaker) — use real videos on the target machine and the
  checklist in the README.
