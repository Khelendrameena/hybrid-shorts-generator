"""Tests for the 2026-11-10 speed/quality pass:
- candidate detection spends a bounded, duration-scaled Laya budget
  (heuristic pre-rank first) instead of up to 120 blind Laya passes;
- Laya predict uses a dynamic max_len instead of always padding to 1024;
- Ollama generation health-gates: offline / model-missing falls back
  immediately with an actionable reason instead of burning 3 timeouts;
- fallback titles come from the most hook-like sentence, trimmed on a
  word boundary, not a raw mid-word transcript cut.
"""
from backend.analysis import candidate_detector
from backend.config import settings
from backend.generation.metadata_generator import fallback_metadata
from backend.models.laya_engine import LayaEngine
from backend.models.ollama_engine import OllamaEngine

_SCORES = {"hook_strength": 80, "emotional_intensity": 80, "information_value": 80,
           "standalone_context": 80, "story_completeness": 80, "speech_clarity": 80,
           "visual_suitability": 80}


class _CountingLaya:
    def __init__(self):
        self.calls = 0

    def score_candidate(self, text, segments=None, audio_energy=None,
                        start=0.0, end=0.0, face_coverage=0.0):
        self.calls += 1
        return {"scores": dict(_SCORES), "category": "storytelling",
                "reasons": [], "engine": "stub", "engine_note": "test stub"}


def _transcript(n_segments=200, seg_dur=4.0):
    text = ("Kya aap jante hain ye surprising fact jo sabko hairan kar dega "
            "aur kahani mein ek bada twist aayega aaj?")
    segs = []
    for i in range(n_segments):
        s = i * seg_dur
        words = [{"word": w, "start": s + j * 0.2, "end": s + j * 0.2 + 0.18,
                  "probability": 0.95} for j, w in enumerate(text.split())]
        segs.append({"id": i, "start": s, "end": s + seg_dur, "text": text,
                     "words": words, "avg_logprob": -0.1, "no_speech_prob": 0.01})
    return {"segments": segs, "language": "hi", "duration": n_segments * seg_dur}


def test_laya_budget_is_bounded_and_scales_with_duration(monkeypatch):
    import backend.analysis.feature_extractor as fe

    monkeypatch.setattr(fe, "extract_features",
                        lambda *a, **k: {**_SCORES, "has_laughter": False,
                                         "has_question": True})
    stub = _CountingLaya()
    clips = candidate_detector.detect_candidates(
        _transcript(), 800.0, laya=stub, min_score=55)
    # auto budget for 800s = clamp(800//12, 16, 60) = 60, half the old 120
    assert 0 < stub.calls <= 60
    assert len(clips) >= 1


def test_laya_budget_small_for_short_video(monkeypatch):
    import backend.analysis.feature_extractor as fe

    monkeypatch.setattr(fe, "extract_features",
                        lambda *a, **k: {**_SCORES, "has_laughter": False,
                                         "has_question": True})
    stub = _CountingLaya()
    candidate_detector.detect_candidates(
        _transcript(n_segments=90), 360.0, laya=stub, min_score=55)
    # 360s -> budget 30 (was: up to 120 regardless of duration)
    assert 0 < stub.calls <= 30


class _FakeAgent:
    def __init__(self):
        self.seen_max_len = None

    def predict(self, state, questions, max_len=None):
        self.seen_max_len = max_len
        return {"answers": {}}


def test_laya_dynamic_max_len_short_text():
    eng = LayaEngine()
    fake = _FakeAgent()
    eng._agent = fake
    eng._predict("Ek chhoti si kahani hai jo sabko pasand aayegi aaj ke din.")
    assert fake.seen_max_len is not None
    assert 320 <= fake.seen_max_len < settings.laya_max_len


def test_laya_dynamic_max_len_long_text_capped():
    eng = LayaEngine()
    fake = _FakeAgent()
    eng._agent = fake
    eng._predict(" ".join(["shabd"] * 3000))
    assert fake.seen_max_len == settings.laya_max_len


def test_ollama_gate_offline_falls_back_immediately(monkeypatch):
    eng = OllamaEngine()
    monkeypatch.setattr(eng, "health", lambda: {"online": False, "error": "refused"})
    clip = {"id": "clip_gate1", "transcript": "Kuch mazedaar baat hui aaj.",
            "category": "funny"}
    md = eng.generate_metadata(clip)
    assert md["source"] == "fallback"
    assert "offline" in md["fallback_reason"].lower()


def test_ollama_gate_model_missing_mentions_pull(monkeypatch):
    eng = OllamaEngine()
    monkeypatch.setattr(eng, "health",
                        lambda: {"online": True, "models": [], "model_present": False})
    clip = {"id": "clip_gate2", "transcript": "Kuch mazedaar baat hui aaj.",
            "category": "funny"}
    md = eng.generate_metadata(clip)
    assert md["source"] == "fallback"
    assert "ollama pull" in md["fallback_reason"]


def test_ollama_chat_disables_thinking_and_caps_tokens(monkeypatch):
    """qwen3 thinks before answering unless think=False — that hidden
    reasoning is the main per-clip cost now that the model stays loaded."""
    import json

    import httpx

    import backend.models.ollama_engine as oe

    seen: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps({
                "clip_id": "clip_think1", "title": "Sach Jo Sabko Hairan Kar Dega",
                "alternative_titles": ["A", "B", "C"],
                "opening_hook": "Ye sach jaan lo",
                "description": "Ek chhoti si kahani.",
                "hashtags": ["#shorts", "#hindi", "#motivation"],
                "thumbnail_text": "SACH SAMNE",
                "language": "Hindi", "caption_style": "dynamic"})}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, **k):
            seen.update(json or {})
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    eng = OllamaEngine()
    monkeypatch.setattr(eng, "health",
                        lambda: {"online": True, "models": ["qwen3:4b"],
                                 "model_present": True})
    clip = {"id": "clip_think1", "transcript": "Kuch mazedaar baat hui aaj.",
            "category": "funny"}
    md = eng.generate_metadata(clip)
    assert md["source"].startswith("ollama")
    assert seen.get("think") is False
    assert seen.get("options", {}).get("num_predict") == 400


def test_render_without_approved_clips_fails_loudly():
    """Regression: render used to report 'done' with zero approved clips —
    the user saw success but no file existed anywhere."""
    import pytest

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app)
    r = c.post("/api/projects/youtube",
               json={"url": "https://www.youtube.com/watch?v=ren123", "title": "R"})
    assert r.status_code == 200
    pid = r.json()["id"]
    r = c.post(f"/api/projects/{pid}/render")
    assert r.status_code == 200
    job = r.json()
    assert job["stage"] == "failed"
    assert "Approve" in (job.get("error") or "")


def test_fallback_title_prefers_hook_sentence():
    clip = {"id": "clip_fb",
            "transcript": ("Aaj hum ek aam si baat karenge jo sab ko pata hai aur "
                           "isme kuch khaas nahi hai. Kya aap jante hain ki sach "
                           "mein hua kya tha us din? Phir sab hasne lage."),
            "category": "storytelling"}
    fb = fallback_metadata(clip)
    assert "Kya aap jante hain" in fb["title"]
    assert not fb["title"].endswith(" hai…")  # not a mid-thought raw cut
