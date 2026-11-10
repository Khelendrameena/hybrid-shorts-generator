"""Model B — OLLAMA Creative Generation Engine (local, default qwen3:4b).

Ollama does CREATIVE work only. It never touches Laya's timestamps or scores —
its input is the already-selected clip (transcript + metadata) and its output
is presentation metadata. Structured output is requested via Ollama's `format`
JSON-schema parameter; output is still parsed defensively (qwen3 may emit
<think> blocks), validated, retried up to 3 times, and finally replaced by a
deterministic fallback so a clip is never left without metadata.
VRAM: requests send keep_alive from settings (default "0" = unload right after
generation) so the 4B model never sits in the RTX 3050's 4 GB next to Whisper/Laya.
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import settings
from .manager import model_manager

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "clip_id": {"type": "string"},
        "title": {"type": "string"},
        "alternative_titles": {"type": "array", "items": {"type": "string"}},
        "opening_hook": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "language": {"type": "string"},
        "caption_style": {"type": "string", "enum": ["dynamic", "classic", "minimal", "bold-yellow"]},
    },
    "required": ["clip_id", "title", "opening_hook", "description", "hashtags",
                 "thumbnail_text", "language", "caption_style"],
}


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    t = re.sub(r"^```(json)?|```$", "", t.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


class OllamaEngine:
    def __init__(self, url: str | None = None, model: str | None = None):
        self.url = (url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model

    # -- health -------------------------------------------------------------
    def health(self) -> dict:
        try:
            with httpx.Client(trust_env=False, timeout=5) as c:
                r = c.get(f"{self.url}/api/tags")
                if r.status_code == 200:
                    models = [m.get("name") for m in r.json().get("models", [])]
                    return {"online": True, "models": models,
                            "model_present": self.model in models or
                            any((m or "").split(":")[0] == self.model.split(":")[0] for m in models)}
                return {"online": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"online": False, "error": str(e)[:200]}

    def _gate_reason(self) -> str | None:
        """None if generation is worth attempting, else why it would fail."""
        h = self.health()
        if not h.get("online"):
            return (f"Ollama offline at {self.url} ({h.get('error', 'no response')}). "
                    f"Start Ollama, or check OLLAMA_URL.")
        if not h.get("model_present"):
            return (f"Ollama model '{self.model}' is not pulled. "
                    f"Run: ollama pull {self.model}")
        return None

    def unload(self) -> bool:
        """Tell Ollama to evict the model from VRAM immediately."""
        try:
            with httpx.Client(trust_env=False, timeout=10) as c:
                r = c.post(f"{self.url}/api/generate",
                           json={"model": self.model, "keep_alive": 0})
                return r.status_code in (200, 204)
        except Exception:
            return False

    # -- generation -----------------------------------------------------------
    def _prompt(self, clip: dict, language: str) -> str:
        return f"""You create metadata for ONE YouTube Short. Reply with ONLY valid JSON matching the schema. No markdown, no explanation, no thinking out loud.

Clip ID: {clip['id']}
Detected category: {clip.get('category', 'general')}
Clip score: {clip.get('score', '')}/100
Target metadata language style: {language} (choose Hindi, English or Hinglish — whichever fits the transcript best; Hinglish = Hindi in Latin/English mix like the transcript)
Transcript of the clip:
\"\"\"{(clip.get('transcript') or '')[:1800]}\"\"\"

Rules:
- title: catchy, <= 60 characters, no clickbait lies, in the transcript's language style.
- alternative_titles: exactly 3 more title options.
- opening_hook: the first on-screen line, <= 12 words, creates curiosity.
- description: 1-2 short sentences.
- hashtags: 4-7 items, each starting with #, always include #shorts.
- thumbnail_text: 2-4 words, ALL CAPS is okay.
- caption_style: one of dynamic, classic, minimal, bold-yellow.
- language: Hindi, English or Hinglish.
Return keys: clip_id, title, alternative_titles, opening_hook, description, hashtags, thumbnail_text, language, caption_style."""

    def generate_metadata(self, clip: dict, language: str = "auto",
                          keep_alive: str | None = None) -> dict:
        model_manager.acquire("ollama")
        # Health gate FIRST: if the server is offline or the model was never
        # pulled, 3 generation attempts would each burn a long timeout for a
        # guaranteed failure. Fall back immediately with an actionable reason.
        gate = self._gate_reason()
        if gate:
            from ..generation.metadata_generator import fallback_metadata

            fb = fallback_metadata(clip, language)
            fb["source"] = "fallback"
            fb["fallback_reason"] = gate
            return fb
        last_err = None
        for attempt in range(3):
            try:
                with httpx.Client(trust_env=False, timeout=settings.ollama_timeout) as c:
                    r = c.post(f"{self.url}/api/chat", json={
                        "model": self.model, "stream": False,
                        "format": METADATA_SCHEMA,
                        # qwen3 is a *thinking* model: by default it burns
                        # hundreds of tokens reasoning before answering, even
                        # with "no thinking" in the prompt. think=False turns
                        # that off server-side (ignored by older Ollama).
                        # num_predict caps the JSON answer (~250 tokens) so a
                        # rambling generation can't eat minutes per clip.
                        "think": False,
                        "keep_alive": keep_alive or settings.ollama_keep_alive,
                        "options": {"temperature": 0.4, "num_ctx": 4096,
                                    "num_predict": 400},
                        "messages": [
                            {"role": "system", "content": "You output only valid JSON."},
                            {"role": "user", "content": self._prompt(clip, language)},
                        ],
                    })
                    r.raise_for_status()
                    content = r.json().get("message", {}).get("content", "")
                data = extract_json(content)
                if data:
                    from ..generation.json_validator import validate_metadata

                    ok, cleaned, errs = validate_metadata(data, clip["id"])
                    if ok:
                        cleaned["source"] = f"ollama:{self.model}"
                        return cleaned
                    last_err = "; ".join(errs)
                else:
                    last_err = "No JSON in Ollama response"
            except Exception as e:
                last_err = str(e)[:250]
        # Deterministic fallback — never leave a clip bare.
        from ..generation.metadata_generator import fallback_metadata

        fb = fallback_metadata(clip, language)
        fb["source"] = "fallback"
        fb["fallback_reason"] = last_err or "unknown"
        return fb
