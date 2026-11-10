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


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?।]\s+", (text or "").strip())
    return [p.strip(" .!?।") for p in parts if p and p.strip()]


def _first_sentence(text: str) -> str:
    s = _sentences(text)
    return s[0] if s else ""


def _trim(text: str, limit: int) -> str:
    """Trim at a word boundary — never mid-word with a dangling ellipsis cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut + "…") if cut else text[:limit]


_HOOK_HINT = re.compile(
    r"(\?|!|\d|kya |kyun |kaise |kabhi |suno|dekho|socho| sach |jhooth|galat|"
    r"secret|truth|never|always|stop|shocking|amazing)", re.I)


def _sentence_score(s: str) -> float:
    words = s.split()
    if not words:
        return -1.0
    score = 0.0
    if _HOOK_HINT.search(s):
        score += 30
    if "?" in s:
        score += 15
    if 5 <= len(words) <= 16:  # title-sized: not a fragment, not a ramble
        score += 20
    elif len(words) < 4:
        score -= 15
    return score


def fallback_metadata(clip: dict, language: str = "auto") -> dict:
    text = clip.get("transcript") or ""
    sents = _sentences(text)
    first = sents[0] if sents else ""
    # Title from the most hook-like sentence, not blindly the first words of
    # the transcript (the old behaviour produced truncated raw transcript as
    # the "title", which looked broken in the Editor).
    ranked = sorted(sents, key=_sentence_score, reverse=True)
    best = ranked[0] if ranked else ""
    title = _trim(best, 60) if best else "Must Watch Moment"
    hook_src = first if first and len(first.split()) <= 14 else (best or first)
    lang = "Hindi" if _DEVANAGARI.search(text) else "English"
    if language in ("Hindi", "English", "Hinglish"):
        lang = language
    tags = ["#shorts"] + _CATEGORY_TAGS.get(clip.get("category", "neutral"), ["#viral"])
    words = (best or first).split()
    thumb = " ".join(words[:3]).upper() if words else "MUST WATCH"
    alts = [_trim(s, 60) for s in ranked[1:3] if _trim(s, 60) != title]
    return {
        "clip_id": clip["id"],
        "title": title,
        "alternative_titles": alts or [title],
        "opening_hook": _trim(hook_src, 110) or title,
        "description": _trim(text, 180),
        "hashtags": tags,
        "thumbnail_text": thumb[:40],
        "language": lang,
        "caption_style": "dynamic",
    }
