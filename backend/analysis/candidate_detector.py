"""Candidate generation over the COMPLETE timeline — never fixed intervals.

Strategy: sliding windows anchored on transcript segments.
  - Windows grow segment-by-segment from every segment start until they reach
    the preferred max duration (60s default); a window is emitted at each
    sentence boundary once it passes the minimum duration (15s). This yields
    many OVERLAPPING candidates with clean sentence edges by construction.
  - Windows are pre-filtered cheaply (word count, speech density) before the
    expensive Laya pass, then Laya+heuristics score them, timestamps are
    optimized on word boundaries, duplicates are removed (timeline IoU),
    a repetition penalty is applied against already-selected clips, and the
    top-N above the minimum score are returned.
"""
from __future__ import annotations

import re
import uuid

from ..config import settings
from ..models.laya_engine import LayaEngine
from ..video.face_tracker import dominant_face_center
from . import timestamp_optimizer
from .deduplication import deduplicate
from .scoring import final_score, repetition_penalty_for

_SENT_END = re.compile(r"[.!?।]\s*$")


def _window_text(segs: list[dict]) -> str:
    return " ".join(s["text"] for s in segs).strip()


def generate_windows(segments: list[dict], min_dur: float, pref_max: float) -> list[dict]:
    windows: list[dict] = []
    n = len(segments)
    for i in range(n):
        start = segments[i]["start"]
        bucket: list[dict] = []
        for j in range(i, n):
            bucket.append(segments[j])
            dur = segments[j]["end"] - start
            if dur > pref_max * 1.6:  # hard stop well past preferred max
                break
            if dur >= min_dur and _SENT_END.search(segments[j]["text"].strip() or " "):
                windows.append({"start": start, "end": segments[j]["end"],
                                "segments": list(bucket), "text": _window_text(bucket)})
            if dur >= pref_max:
                break
    return windows


def detect_candidates(transcript: dict, video_duration: float,
                      audio_energy: list[dict] | None = None,
                      face_track: list[dict] | None = None,
                      laya: LayaEngine | None = None, progress_cb=None,
                      max_clips: int | None = None, min_score: float | None = None) -> list[dict]:
    segments = transcript.get("segments") or []
    if not segments:
        return []
    laya = laya or LayaEngine()
    max_clips = max_clips or settings.max_clips
    min_score = settings.min_clip_score if min_score is None else min_score

    windows = generate_windows(segments, settings.min_clip_duration, settings.preferred_max_duration)
    # Cheap pre-filter: enough words to be a real moment, sorted by a density
    # heuristic so Laya spends its passes on the most promising windows first.
    windows = [w for w in windows if len(w["text"].split()) >= 25]
    windows.sort(key=lambda w: (w["text"].count("?") + w["text"].count("!"), len(w["text"])), reverse=True)
    windows = windows[:120]  # bounded Laya workload per video

    scored: list[dict] = []
    total = max(1, len(windows))
    for idx, w in enumerate(windows):
        _, _, face_cov = dominant_face_center(face_track or [], w["start"], w["end"])
        result = laya.score_candidate(w["text"], w["segments"], audio_energy,
                                      w["start"], w["end"], face_cov)
        score = final_score(result["scores"])
        if score < min_score - 15:  # keep near-misses for penalty pass, drop the rest
            continue
        start, end, notes = timestamp_optimizer.optimize(w["start"], w["end"], segments, video_duration)
        if end - start < settings.min_clip_duration * 0.8:
            continue
        scored.append({
            "id": f"clip_{uuid.uuid4().hex[:8]}", "start": start, "end": end,
            "duration": round(end - start, 2), "transcript": w["text"],
            "scores": result["scores"], "score": score, "category": result["category"],
            "reasons": result["reasons"] + ([f"Timestamp: {k}" for k, v in notes.items() if v]),
            "engine": result["engine"], "engine_note": result["engine_note"],
        })
        if progress_cb:
            progress_cb(idx / total * 100.0, f"Laya analysis… {idx + 1}/{total} windows")

    # Dedup by timeline overlap, then repetition penalty vs selected, re-rank.
    kept = deduplicate(scored, iou_threshold=0.45)
    final: list[dict] = []
    for c in kept:
        pen = max((repetition_penalty_for(c["transcript"], s["transcript"]) for s in final), default=0.0)
        c["repetition_penalty"] = pen
        c["score"] = final_score(c["scores"], pen)
        if c["score"] >= min_score:
            final.append(c)
        if len(final) >= max_clips:
            break
    final.sort(key=lambda c: c["start"])
    for i, c in enumerate(final, 1):  # stable, timeline-ordered ids for humans
        c["display_id"] = f"clip_{i:03d}"
    return final
