import json

from backend.generation.json_validator import validate_metadata
from backend.generation.metadata_generator import fallback_metadata
from backend.models.ollama_engine import extract_json

GOOD = {"clip_id": "clip_001", "title": "You Won't Believe This",
        "alternative_titles": ["A", "B"], "opening_hook": "Wait for it…",
        "description": "A short desc.", "hashtags": ["#shorts", "#facts", "#viral"],
        "thumbnail_text": "SHOCKING", "language": "English", "caption_style": "dynamic"}


def test_validate_good():
    ok, out, errs = validate_metadata(dict(GOOD), "clip_001")
    assert ok, errs
    assert out["clip_id"] == "clip_001"
    assert "#shorts" in out["hashtags"]


def test_validate_adds_shorts_and_fixes_style():
    bad = dict(GOOD, hashtags=["facts"], caption_style="neon-rave", language="Klingon")
    ok, out, _ = validate_metadata(bad, "clip_001")
    assert "#shorts" in out["hashtags"]
    assert out["caption_style"] == "dynamic"
    assert out["language"] == "English"


def test_validate_rejects_missing_title():
    bad = dict(GOOD, title="")
    ok, _, errs = validate_metadata(bad, "clip_001")
    assert not ok and errs


def test_extract_json_handles_think_and_fences():
    raw = '<think>reasoning</think>```json\n{"a": 1}\n```'
    assert extract_json(raw) == {"a": 1}
    assert extract_json('noise {"b": 2} trailing') == {"b": 2}
    assert extract_json("no json here") is None


def test_fallback_metadata_shape_validates():
    clip = {"id": "clip_9", "transcript": "Did you know this one fact changes everything? It is true.",
            "category": "surprising"}
    fb = fallback_metadata(clip)
    ok, _, errs = validate_metadata(fb, "clip_9")
    assert ok, errs
    json.dumps(fb)  # must be JSON-serialisable
