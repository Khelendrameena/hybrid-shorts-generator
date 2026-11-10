"""Timestamp optimization — the difference between a usable Short and a
mid-sentence chop. Works on WORD timestamps so cuts never split a word:
  - start snaps back to the start of the first word / sentence boundary,
  - end extends to the end of the last complete sentence inside the window,
  - silence at the edges is trimmed using word gaps,
  - configurable padding is added, then clamped to [0, video_duration]
    and to min/max duration rules.
"""
from __future__ import annotations

import re

from ..config import settings

_SENT_END = re.compile(r"[.!?।]$")


def _words_in(segments: list[dict], start: float, end: float) -> list[dict]:
    out = []
    for s in segments:
        for w in s.get("words") or []:
            if w["end"] >= start and w["start"] <= end:
                out.append(w)
    return sorted(out, key=lambda w: w["start"])


def optimize(start: float, end: float, segments: list[dict], video_duration: float,
             padding_before: float | None = None, padding_after: float | None = None) -> tuple[float, float, dict]:
    pb = settings.padding_before if padding_before is None else padding_before
    pa = settings.padding_after if padding_after is None else padding_after
    notes: dict = {"snapped_start": False, "extended_end": False, "trimmed_silence": False}
    words = _words_in(segments, start - 2, end + 8)
    if not words:
        return round(max(0.0, start - pb), 3), round(min(video_duration, end + pa), 3), notes

    # 1) Start: first word at/after `start` (never mid-word, never mid-sentence
    #    when the previous word ends a sentence within 1.5s before it).
    first = next((w for w in words if w["start"] >= start - 0.05), words[0])
    new_start = float(first["start"])
    if abs(new_start - start) > 0.01:
        notes["snapped_start"] = True

    # 2) End: extend forward to the end of the current sentence (max +6s,
    #    never past max duration).
    last_in = [w for w in words if w["start"] <= end]
    new_end = float(last_in[-1]["end"]) if last_in else end
    idx = words.index(last_in[-1]) if last_in else -1
    steps = 0
    while 0 <= idx < len(words) - 1 and steps < 80:
        w = words[idx]
        if _SENT_END.search((w.get("word") or "").strip()):
            break
        nxt = words[idx + 1]
        if nxt["start"] - new_start > settings.max_clip_duration:
            break
        if nxt["start"] - end > 6.0:
            break
        new_end = float(nxt["end"])
        idx += 1
        steps += 1
        notes["extended_end"] = True

    # 3) Trim long edge silences (>0.8s gaps at edges already handled by word snap).
    if new_start - start > 0.8 or end - new_end > 0.8:
        notes["trimmed_silence"] = True

    # 4) Padding + clamps.
    new_start = max(0.0, new_start - pb)
    new_end = min(video_duration, new_end + pa)
    if new_end - new_start > settings.max_clip_duration:
        new_end = new_start + settings.max_clip_duration
    return round(new_start, 3), round(new_end, 3), notes
