"""Strict validation + cleaning for Ollama-generated metadata.
Anything invalid is rejected (caller retries, then falls back) — malformed
metadata never reaches the editor or the export."""
from __future__ import annotations

import re

STYLES = {"dynamic", "classic", "minimal", "bold-yellow"}
LANGS = {"Hindi", "English", "Hinglish"}


def validate_metadata(data: dict, expected_clip_id: str) -> tuple[bool, dict, list[str]]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return False, {}, ["output is not a JSON object"]
    out: dict = {}
    out["clip_id"] = expected_clip_id  # trust our id, not the model's

    title = str(data.get("title") or "").strip()
    if not title:
        errs.append("title missing")
    out["title"] = title[:80]

    alts = data.get("alternative_titles") or []
    if isinstance(alts, str):
        alts = [alts]
    out["alternative_titles"] = [str(a).strip()[:80] for a in alts if str(a).strip()][:3]

    hook = str(data.get("opening_hook") or "").strip()
    if not hook:
        errs.append("opening_hook missing")
    out["opening_hook"] = hook[:120]

    out["description"] = str(data.get("description") or "").strip()[:300]

    tags = data.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    clean_tags = []
    for t in tags:
        t = str(t).strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + re.sub(r"\s+", "", t)
        clean_tags.append(t[:40])
    if "#shorts" not in [t.lower() for t in clean_tags]:
        clean_tags.insert(0, "#shorts")
    out["hashtags"] = clean_tags[:7]
    if len(clean_tags) < 3:
        errs.append("too few hashtags")

    out["thumbnail_text"] = str(data.get("thumbnail_text") or title).strip()[:40]

    lang = str(data.get("language") or "English").strip().title()
    out["language"] = lang if lang in LANGS else "English"

    style = str(data.get("caption_style") or "dynamic").strip().lower()
    out["caption_style"] = style if style in STYLES else "dynamic"

    return (len(errs) == 0), out, errs
