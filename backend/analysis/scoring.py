"""Configurable weighted scoring (spec section 5).

Final = 0.20*Hook + 0.15*Emotion + 0.15*Info + 0.15*Standalone + 0.15*Story
      + 0.10*Clarity + 0.10*Visual  −  RepetitionPenalty
clamped to 0–100. Scores estimate engagement potential — never guaranteed virality.
"""
from __future__ import annotations

from ..config import settings
from .feature_extractor import clamp

COMPONENTS = ("hook_strength", "emotional_intensity", "information_value",
              "standalone_context", "story_completeness", "speech_clarity",
              "visual_suitability")


def final_score(scores: dict, repetition_penalty: float = 0.0,
                weights: dict | None = None) -> float:
    w = weights or settings.weights
    total_w = sum(w.get(k, 0) for k in COMPONENTS) or 1.0
    weighted = sum(float(scores.get(k, 0)) * w.get(k, 0) for k in COMPONENTS) / total_w
    # If custom weights don't sum to 1, normalise; with defaults (sum=1.0) this is identity.
    return round(clamp(weighted - float(repetition_penalty)), 1)


def repetition_penalty_for(text_a: str, text_b: str) -> float:
    """Jaccard overlap of word 3-grams → penalty 0..30 for near-duplicates."""
    def grams(t: str) -> set:
        ws = (t or "").lower().split()
        return {" ".join(ws[i:i + 3]) for i in range(max(0, len(ws) - 2))}

    a, b = grams(text_a), grams(text_b)
    if not a or not b:
        return 0.0
    j = len(a & b) / max(1, len(a | b))
    return round(j * 30.0, 1)
