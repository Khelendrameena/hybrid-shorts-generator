"""YouTube captions as a transcript source (user request, 2026-11-10):
transcription is the slowest stage, so when the video itself has captions
on YouTube — uploaded (manual) subtitles first, YouTube's auto-captions
second — take them straight from YouTube in seconds and skip Faster-Whisper
entirely. Videos without usable captions fall back to Whisper unchanged;
local files always use Whisper.

Output is the EXACT transcript schema Whisper produces
({language, duration, segments: [{start, end, text, words, ...}], full_text}),
saved as transcript.json + transcript.srt in the project dir, so every
downstream stage (candidates, Laya, subtitles, export) works untouched.

Honest limitations, by design:
- Caption tracks carry line-level timing, not word-level timing. Word
  timestamps are synthesised by distributing each line's duration across
  its words proportionally to word length — good enough for the karaoke
  highlight (a word may light up a fraction early/late), and flagged with
  probability 0.9 instead of Whisper's real per-word confidence.
- Auto-captions are YouTube's own ASR: usually better than Whisper-small
  on clean speech, worse on dialect-heavy audio. Manual captions win when
  both exist.
- Only an ORIGINAL-language auto track is accepted (a '-orig' key or a
  hi/en match). yt-dlp lists 100+ machine-translated tracks too; picking
  one of those by accident would silently change the video's language.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
from pathlib import Path

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ---------------------------------------------------------------- parsing

def _synth_words(text: str, start: float, end: float) -> list[dict]:
    """Approximate word timings: split the line's duration across words,
    weighted by word length (longer words take longer to say)."""
    tokens = [t for t in text.split() if t]
    if not tokens:
        return []
    dur = max(0.05, end - start)
    weights = [len(t) + 1 for t in tokens]
    total = sum(weights) or 1
    words, t = [], start
    for tok, w in zip(tokens, weights):
        d = dur * w / total
        words.append({"word": tok, "start": round(t, 3), "end": round(min(end, t + d), 3),
                      "probability": 0.9})
        t += d
    return words


def _segments_from_cues(cues: list[tuple[float, float, str]]) -> list[dict]:
    """Cues (start, end, text) -> Whisper-schema segments, with the same
    pause-based speaker_turn heuristic Whisper uses (>1.2s gap)."""
    segments: list[dict] = []
    turn, prev_end = 0, 0.0
    for start, end, text in cues:
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        if not text or end <= start:
            continue
        # Music-only markers ("[♪♪♪]", "[Music]") are not speech — Whisper
        # would never emit them, and Laya should not score them as content.
        _bare = text.strip("[]() ").replace("♪", "").replace("♫", "").strip()
        if not _bare or _bare.lower() == "music":
            continue
        if segments and text == segments[-1]["text"]:
            segments[-1]["end"] = round(end, 3)  # rolling-caption repeat: extend
            segments[-1]["words"] = _synth_words(text, segments[-1]["start"], end)
            prev_end = end
            continue
        if start - prev_end > 1.2 and segments:
            turn += 1
        segments.append({
            "id": len(segments), "start": round(start, 3), "end": round(end, 3),
            "text": text, "words": _synth_words(text, start, end),
            "avg_logprob": -0.1, "no_speech_prob": 0.0,
            "speaker_turn": turn,  # heuristic hint only — NOT diarization
        })
        prev_end = end
    return segments


def parse_json3(data: dict) -> list[dict]:
    """YouTube json3 caption format -> segments."""
    cues = []
    for ev in data.get("events") or []:
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs)
        if not text.strip():
            continue
        start = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 0) / 1000.0
        cues.append((start, start + max(dur, 0.4), text))
    return _segments_from_cues(cues)


_VTT_TS = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})")


def _vtt_time(s: str) -> float:
    m = _VTT_TS.match(s.strip())
    if not m:
        return 0.0
    h, mi, se, ms = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se + ms / 1000.0


def parse_vtt(text: str) -> list[dict]:
    """WebVTT caption format -> segments (tags stripped)."""
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        arrow = next((ln for ln in lines if "-->" in ln), None)
        if not arrow:
            continue
        a, b = arrow.split("-->")[0], arrow.split("-->")[1].split()[0]
        body = " ".join(ln for ln in lines if "-->" not in ln and not ln.startswith(("WEBVTT", "Kind:", "Language:")))
        body = re.sub(r"<[^>]+>", "", body)
        if body.strip():
            cues.append((_vtt_time(a), _vtt_time(b), body))
    return _segments_from_cues(cues)


# ------------------------------------------------------- track selection

def pick_track(info: dict, preferred: str | None = None) -> tuple[str, str, list[dict]] | None:
    """Choose (language, kind, formats): manual subtitles beat auto-captions;
    inside each, an explicit user language beats hi/en defaults; for
    auto-captions only an original-language track ('-orig' or hi/en) is
    accepted so a machine translation is never picked by accident."""
    pref = (preferred or "").strip().lower()
    bases = [pref] if pref and pref != "auto" else ["hi", "en"]

    def match(tracks: dict, allow_any: bool) -> tuple[str, list[dict]] | None:
        if not tracks:
            return None
        for base in bases:
            if base in tracks:
                return base, tracks[base]
            for key in sorted(tracks):
                if key.startswith(base + "-") or key == base:
                    return key, tracks[key]
        for key in sorted(tracks):  # original-language auto track
            if key.endswith("-orig"):
                return key, tracks[key]
        if allow_any:  # manual subs in any language still beat Whisper
            key = sorted(tracks)[0]
            return key, tracks[key]
        return None

    manual = match(info.get("subtitles") or {}, allow_any=True)
    if manual:
        return manual[0], "manual", manual[1]
    auto = match(info.get("automatic_captions") or {}, allow_any=False)
    if auto:
        return auto[0], "auto", auto[1]
    return None


def _pick_format_url(formats: list[dict]) -> tuple[str, str] | None:
    """Prefer json3 (cleanest timing), fall back to vtt."""
    for ext in ("json3", "vtt"):
        for f in formats or []:
            if f.get("ext") == ext and f.get("url"):
                return ext, f["url"]
    return None


# ---------------------------------------------------------------- fetch

def fetch_youtube_captions(url: str, out_dir: str | Path,
                           preferred_language: str | None = None,
                           progress_cb=None) -> dict | None:
    """Download captions for a YouTube URL and save them as the project's
    transcript. Returns the transcript dict, or None when no usable caption
    track exists / anything fails — the caller then falls back to Whisper."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return None
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                               "socket_timeout": 30}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None
    if not info:
        return None

    picked = pick_track(info, preferred_language)
    if not picked:
        return None
    lang, kind, formats = picked
    fmt = _pick_format_url(formats)
    if not fmt:
        return None
    ext, track_url = fmt
    try:
        req = urllib.request.Request(track_url, headers=_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        segments = parse_json3(json.loads(raw)) if ext == "json3" else parse_vtt(raw)
    except Exception:
        return None
    if len(segments) < 3 or segments[-1]["end"] <= 0:
        return None

    base_lang = lang.replace("-orig", "").split("-")[0]
    result = {
        "language": base_lang, "language_probability": 1.0,
        "duration": segments[-1]["end"],
        "model": f"youtube-captions ({kind}: {lang})", "device": "youtube",
        "source": "youtube_captions", "caption_kind": kind, "caption_lang": lang,
        "segments": segments,
        "full_text": " ".join(s["text"] for s in segments),
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from .whisper_engine import segments_to_srt  # local import: no cycle

    (out_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "transcript.srt").write_text(segments_to_srt(segments), encoding="utf-8")
    if progress_cb:
        progress_cb(100.0, f"YouTube captions mile ({kind}, {base_lang}) — "
                           f"{len(segments)} lines, Whisper skip ho gaya")
    return result
