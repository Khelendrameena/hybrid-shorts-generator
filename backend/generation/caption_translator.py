"""Caption language (user request, 2026-11-11): the user picks WHICH language
the captions — and the Short's own text (title / hook / description) — should
be in, independent of the language spoken in the video.

Settings value `caption_language`: auto | hindi | english | hinglish.
- auto: captions stay in the spoken language, metadata follows the
  transcript (the old behaviour).
- hindi / english / hinglish: caption lines are TRANSLATED locally with
  Ollama (qwen3:4b) — no paid APIs — and metadata generation is instructed
  to write in that language too (see jobs/queue.py).

Translation notes (honest):
- Timing is never changed: only each segment's TEXT is replaced, and word
  timings for the karaoke subtitle highlight are re-synthesised
  proportionally (same approach as the YouTube-captions path).
- If Ollama is offline / the model is missing / a batch comes back with the
  wrong line count twice, the ORIGINAL captions are kept and the caller
  gets a reason string — a render must never fail over a translation.
"""
from __future__ import annotations

import re

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

TARGETS = {
    "hindi": {"name": "Hindi", "detail": "Hindi written in Devanagari script (हिन्दी)",
              "code": "hi", "metadata_name": "Hindi"},
    "english": {"name": "English", "detail": "English",
                "code": "en", "metadata_name": "English"},
    "hinglish": {"name": "Hinglish", "detail": "Hinglish — Hindi written in Roman/Latin letters, the way Indians chat (e.g. 'ye baat bilkul sahi hai')",
                 "code": "hi", "metadata_name": "Hinglish"},
}

BATCH = 25


def metadata_language(target_key: str | None) -> str | None:
    """'Hindi' | 'English' | 'Hinglish' for the metadata generator, or None
    when the setting is auto/unknown (generator then follows the transcript)."""
    t = TARGETS.get((target_key or "").strip().lower())
    return t["metadata_name"] if t else None


def needs_translation(segments: list[dict], transcript_lang: str | None,
                      target_key: str | None) -> bool:
    """Decide whether the caption text must be (trans)written at all — skip
    the Ollama call entirely when the captions are already in the target."""
    t = TARGETS.get((target_key or "").strip().lower())
    if t is None or not segments:
        return False
    sample = " ".join(s.get("text", "") for s in segments[:12])
    has_devanagari = bool(_DEVANAGARI.search(sample))
    lang = (transcript_lang or "").split("-")[0].lower()
    if t["code"] == "en":
        return lang != "en"
    if target_key == "hindi":  # wants Devanagari Hindi
        return not (lang == "hi" and has_devanagari)
    if target_key == "hinglish":  # wants Roman-script Hindi
        return has_devanagari or lang == "en"
    return False


def _ollama_chat_lines(lines: list[str], target: dict, engine) -> list[str] | None:
    """One batch through Ollama with a strict JSON schema; None on failure."""
    import httpx

    from ..config import settings

    schema = {"type": "object",
              "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
              "required": ["lines"]}
    numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(lines))
    prompt = (f"Translate each numbered caption line into {target['detail']}. "
              f"Keep the SAME numbering and the SAME number of lines ({len(lines)}). "
              f"Keep each line short like a subtitle. Do not add or remove lines, "
              f"do not merge lines. Reply with ONLY JSON: {{\"lines\": [\"...\", ...]}}\n\n"
              f"{numbered}")
    try:
        with httpx.Client(trust_env=False, timeout=settings.ollama_timeout) as c:
            r = c.post(f"{engine.url}/api/chat", json={
                "model": engine.model, "stream": False, "format": schema,
                "think": False, "keep_alive": "5m",
                "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 1200},
                "messages": [{"role": "system", "content": "You output only valid JSON."},
                             {"role": "user", "content": prompt}],
            })
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "")
    except Exception:
        return None
    from ..models.ollama_engine import extract_json

    data = extract_json(content)
    out = (data or {}).get("lines")
    if isinstance(out, list) and len(out) == len(lines) and all(str(x).strip() for x in out):
        return [str(x).strip() for x in out]
    return None


def translate_segments(segments: list[dict], target_key: str, engine=None,
                       chat_fn=None) -> tuple[list[dict], str]:
    """Return (segments_to_use, note). On success the note says the captions
    were translated; on ANY failure the ORIGINAL segments come back with the
    reason — rendering proceeds either way."""
    t = TARGETS.get((target_key or "").strip().lower())
    if t is None:
        return segments, "caption language auto — original captions"
    if engine is None and chat_fn is None:
        from ..models.ollama_engine import OllamaEngine

        engine = OllamaEngine()
    if chat_fn is None:
        gate = engine._gate_reason()
        if gate:
            return segments, f"captions original hi rahe — {gate}"

    from ..transcription.youtube_captions import _synth_words

    texts = [s.get("text", "") for s in segments]
    translated: list[str] = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        out = None
        for _attempt in range(2):
            got = (chat_fn(batch, t) if chat_fn is not None
                   else _ollama_chat_lines(batch, t, engine))
            # Count check HERE, not only inside the Ollama caller: a short
            # batch must never slip through — zip() would silently drop
            # caption lines and shift every later line onto the wrong timing.
            if (isinstance(got, list) and len(got) == len(batch)
                    and all(str(x).strip() for x in got)):
                out = [str(x).strip() for x in got]
                break
        if out is None:
            return segments, (f"captions original hi rahe — {t['name']} translation "
                              f"batch {i // BATCH + 1} do baar fail hua (line count/format)")
        translated.extend(out)

    new_segments = []
    for seg, new_text in zip(segments, translated):
        ns = dict(seg)
        ns["text"] = new_text
        ns["words"] = _synth_words(new_text, float(seg["start"]), float(seg["end"]))
        ns["translated_to"] = t["name"]
        new_segments.append(ns)
    return new_segments, f"captions {t['name']} me translate ho gaye (Ollama, {len(translated)} lines)"
