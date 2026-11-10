"""Duplicate / overlap suppression: two clips that cover mostly the same
timeline or mostly the same words are the same Short. Keeps the higher score."""
from __future__ import annotations


def time_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return inter / union if union > 0 else 0.0


def _is_dup(a: dict, b: dict, iou_threshold: float) -> bool:
    if time_iou(a["start"], a["end"], b["start"], b["end"]) > iou_threshold:
        return True
    # Containment: a short clip almost entirely inside a longer one is the
    # same moment even when IoU is low (17s inside 60s → IoU only 0.30).
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    shorter = min(a["end"] - a["start"], b["end"] - b["start"])
    return shorter > 0 and inter / shorter > 0.8


def deduplicate(clips: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    """Input sorted by score desc (or not — we sort). Returns kept clips."""
    ordered = sorted(clips, key=lambda c: c.get("score", 0), reverse=True)
    kept: list[dict] = []
    for c in ordered:
        if not any(_is_dup(c, k, iou_threshold) for k in kept):
            kept.append(c)
    return kept
