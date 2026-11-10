"""Deterministic fallback metadata — used ONLY when Ollama is offline or its
JSON fails validation 3 times. Honest, transcript-derived, never invented facts."""
from __future__ import annotations

import re

_CATEGORY_TAGS = {
    "funny": ["#funny", "#comedy"], "emotional": ["#emotional", "#feelings"],
    "educational": ["#education", "#facts"], "controversial": ["#debate", "#opinion"],
    "surprising": ["#shocking", "#didyouknow"], "storytelling": ["#story", "#storytime"],
    "neutral": ["#viral"],
}
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _first_sentence(text: str) -> str:
    parts = re.split(r"[.!?।]\s+", (text or "").strip())
    return parts[0].strip() if parts else ""


def fallback_metadata(clip: dict, language: str = "auto") -> dict:
    text = clip.get("transcript") or ""
    first = _first_sentence(text)
    title = (first[:57] + "…") if len(first) > 60 else (first or "Must Watch Moment")
    if not title:
        title = "Must Watch Moment"
    lang = "Hindi" if _DEVANAGARI.search(text) else "English"
    if language in ("Hindi", "English", "Hinglish"):
        lang = language
    tags = ["#shorts"] + _CATEGORY_TAGS.get(clip.get("category", "neutral"), ["#viral"])
    words = first.split()
    thumb = " ".join(words[:3]).upper() if words else "MUST WATCH"
    return {
        "clip_id": clip["id"],
        "title": title,
        "alternative_titles": [title, f"{title} | Part 1", thumb.title()],
        "opening_hook": first[:120] or title,
        "description": (text[:180] + "…") if len(text) > 180 else text,
        "hashtags": tags,
        "thumbnail_text": thumb[:40],
        "language": lang,
        "caption_style": "dynamic",
    }
