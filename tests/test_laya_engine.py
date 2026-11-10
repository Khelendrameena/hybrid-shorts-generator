"""Laya engine: parsing of the REAL typed-answer shapes + heuristic fallback
path (used when the laya package is absent — the fallback must still produce
valid, in-range component scores and must honestly label its engine)."""
from backend.models.laya_engine import (
    LayaEngine, _choice_prob, _noul_prob, _score_expected)

HOOKY = ("What if everything you knew about money was wrong? This shocking fact "
         "changes everything. Most people make this one mistake every single day "
         "and lose thousands without knowing. Here is the simple truth nobody "
         "tells you, and the exact step to fix it today. Remember this forever.")
FLAT = ("So then we went to the next topic and discussed some routine points "
        "about the schedule and other normal things for a while without anything "
        "particularly notable happening in this part of the meeting at all today.")


def test_noul_parsing():
    assert _noul_prob({"noul": 0.83}) == 0.83
    assert _noul_prob({}) is None
    assert _noul_prob({"noul": "high"}) is None


def test_choice_parsing():
    ans = {"choice": "A", "probabilities": {"A": 0.9, "B": 0.1}}
    assert _choice_prob(ans, "A") == 0.9
    assert _choice_prob(ans, "B") == 0.1


def test_score_expected_from_distribution():
    ans = {"probabilities": {"low": 0.0, "medium": 0.0, "high": 0.0, "very_high": 1.0}}
    assert _score_expected(ans, ["low", "medium", "high", "very_high"]) == 100.0
    ans2 = {"probabilities": {"low": 1.0, "medium": 0.0, "high": 0.0, "very_high": 0.0}}
    assert _score_expected(ans2, ["low", "medium", "high", "very_high"]) == 0.0


def test_fallback_scores_in_range_and_hooky_beats_flat():
    eng = LayaEngine()
    a = eng.score_candidate(HOOKY)
    b = eng.score_candidate(FLAT)
    for res in (a, b):
        assert res["engine"] in ("laya", "heuristic-fallback")
        for v in res["scores"].values():
            assert 0 <= v <= 100
        assert res["category"]
        assert res["reasons"]
    # The deterministic features must rank the hooky text higher on hook strength
    # regardless of whether real Laya or the fallback produced the blend.
    assert a["scores"]["hook_strength"] >= b["scores"]["hook_strength"]
