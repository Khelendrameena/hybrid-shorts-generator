"""Central configuration. Env vars > config/default.yaml > defaults in code.

No secrets are hardcoded. There are no paid-API keys in this project at all;
Laya and Ollama are both local. Any future key belongs in .env only.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / os.environ.get("DATA_DIR", "data")
UPLOADS_DIR = DATA_DIR / "uploads"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DB_PATH = DATA_DIR / "shorts.db"

for _d in (DATA_DIR, UPLOADS_DIR, PROJECTS_DIR, CACHE_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_yaml_defaults() -> dict:
    try:
        import yaml  # type: ignore

        p = PROJECT_ROOT / "config" / "default.yaml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


_YAML = _load_yaml_defaults()


def _get(section: str, key: str, env: str, default):
    v = os.environ.get(env)
    if v is not None and v != "":
        return v
    try:
        return _YAML[section][key]
    except Exception:
        return default


def _f(section, key, env, default) -> float:
    return float(_get(section, key, env, default))


def _i(section, key, env, default) -> int:
    return int(_get(section, key, env, default))


class Settings:
    # Laya
    laya_model_id: str = str(_get("laya", "model_id", "LAYA_MODEL_ID", "convaiinnovations/laya-multilingual"))
    laya_device: str = str(_get("laya", "device", "LAYA_DEVICE", "auto"))
    laya_max_len: int = _i("laya", "max_len", "LAYA_MAX_LEN", 1024)
    laya_max_windows: int = _i("laya", "max_windows", "LAYA_MAX_WINDOWS", 0)
    laya_enabled: bool = str(_get("laya", "enabled", "LAYA_ENABLED", "true")).lower() in ("1", "true", "yes")

    # Ollama
    ollama_url: str = str(_get("ollama", "url", "OLLAMA_URL", "http://localhost:11434")).rstrip("/")
    ollama_model: str = str(_get("ollama", "model", "OLLAMA_MODEL", "qwen3:4b"))
    ollama_timeout: int = _i("ollama", "timeout", "OLLAMA_TIMEOUT", 120)
    ollama_keep_alive: str = str(_get("ollama", "keep_alive", "OLLAMA_KEEP_ALIVE", "0"))

    # Whisper
    whisper_model: str = str(_get("whisper", "model", "WHISPER_MODEL", "small"))
    whisper_device: str = str(_get("whisper", "device", "WHISPER_DEVICE", "auto"))
    whisper_compute_type: str = str(_get("whisper", "compute_type", "WHISPER_COMPUTE_TYPE", "default"))

    # Clips / scoring
    max_clips: int = _i("scoring", "max_clips", "MAX_CLIPS", 10)
    min_clip_score: float = _f("scoring", "min_score", "MIN_CLIP_SCORE", 55)
    min_clip_duration: float = _f("clips", "min_duration", "MIN_CLIP_DURATION", 15)
    preferred_max_duration: float = _f("clips", "preferred_max_duration", "PREFERRED_MAX_DURATION", 60)
    max_clip_duration: float = _f("clips", "max_duration", "MAX_CLIP_DURATION", 180)
    padding_before: float = _f("clips", "padding_before", "CLIP_PADDING_BEFORE", 0.4)
    padding_after: float = _f("clips", "padding_after", "CLIP_PADDING_AFTER", 0.6)

    # Render
    output_width: int = _i("render", "width", "OUTPUT_WIDTH", 1080)
    output_height: int = _i("render", "height", "OUTPUT_HEIGHT", 1920)
    subtitle_theme: str = str(_get("render", "subtitle_theme", "SUBTITLE_THEME", "dynamic"))
    # fit = poora frame 9:16 canvas ke andar, khaali jagah blurred bg se bharti
    # hai (kuch cut nahi hota). crop = full-bleed 9:16 crop (sides kat sakte hain).
    frame_mode: str = str(_get("render", "frame_mode", "RENDER_FRAME_MODE", "fit"))
    default_language: str = str(os.environ.get("DEFAULT_LANGUAGE", "auto"))

    # Scoring weights (spec section 5) — configurable, must sum ~1.0 before penalty
    weights: dict = {
        "hook_strength": 0.20,
        "emotional_intensity": 0.15,
        "information_value": 0.15,
        "standalone_context": 0.15,
        "story_completeness": 0.15,
        "speech_clarity": 0.10,
        "visual_suitability": 0.10,
    }
    try:
        _w = _YAML.get("scoring", {}).get("weights", {})
        for k in list(weights):
            if k in _w:
                weights[k] = float(_w[k])
    except Exception:
        pass

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in dir(self) if not k.startswith("_") and not callable(getattr(self, k))}


settings = Settings()
