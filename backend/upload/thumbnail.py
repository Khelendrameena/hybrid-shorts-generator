"""Auto thumbnail: rendered clip se sabse achha frame chuno.

Kai candidate frames nikaal kar har ek ko score karte hain —
sharpness (detail) + rang (saturation), aur fade-in/out wale
kaale/safed frames ko penalty. Jeetne wale frame par metadata ka
thumbnail_text (agar hai aur bold font mil jaye) bada karke lagta hai.
Pillow na ho to beech wala frame seedha use hota hai (fallback).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _extract_frame(video: str, t: float, out: Path) -> bool:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
         "-frames:v", "1", "-q:v", "3", str(out), "-y"],
        capture_output=True, timeout=60)
    return out.exists() and out.stat().st_size > 0


def _score(img_path: Path) -> float:
    """Sharp + rang-biranga frame = zyada score. Kaala/safed fade
    frame ko penalty. PIL/numpy na ho to 0 (beech wala chun lenge)."""
    try:
        import numpy as np
        from PIL import Image
        img = Image.open(img_path).convert("RGB")
        gray = np.asarray(img.convert("L"), dtype=float)
        gx = np.diff(gray, axis=1)
        gy = np.diff(gray, axis=0)
        sharp = float(gx.var() + gy.var())
        arr = np.asarray(img, dtype=float)
        colour = float(arr.std(axis=(0, 1)).mean())
        mean = float(gray.mean())
        score = sharp + 2.0 * colour
        if mean < 15 or mean > 245:  # fade to black/white wala frame
            score *= 0.2
        return score
    except Exception:
        return 0.0


def _draw_text(img_path: Path, text: str) -> None:
    """thumbnail_text ko neeche bade bold letters me lagao.
    Font na mile ya kuch fail ho to bina text wali image hi rehti hai."""
    text = " ".join((text or "").split())[:60]
    if not text:
        return
    font_file = next((f for f in _FONT_CANDIDATES if Path(f).exists()), None)
    if not font_file:
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        words = text.upper().split()
        lines, cur = [], ""
        for word in words:  # max 3 shabd per line, max 2 lines
            trial = f"{cur} {word}".strip()
            if len(trial) <= 16 or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
            if len(lines) == 2:
                break
        if cur and len(lines) < 2:
            lines.append(cur)
        size = max(28, w // 9)
        font = ImageFont.truetype(font_file, size)
        draw = ImageDraw.Draw(img, "RGBA")
        total_h = size * len(lines) + 16 * (len(lines) - 1)
        y = h - total_h - h // 14
        draw.rectangle([0, y - 18, w, y + total_h + 18], fill=(0, 0, 0, 140))
        for line in lines:
            tw = draw.textlength(line, font=font)
            draw.text(((w - tw) / 2, y), line, font=font, fill=(255, 255, 255),
                      stroke_width=max(2, size // 14), stroke_fill=(0, 0, 0))
            y += size + 16
        img.save(img_path, "JPEG", quality=90)
    except Exception:
        pass


def pick_thumbnail(video_path: str, out_path: str | Path,
                   text: str = "") -> str:
    """Best frame chun kar JPEG (max 2MB, YouTube ki limit) bachao."""
    from ..video.metadata import probe
    info = probe(video_path)
    dur = info.get("duration") or 0
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fractions = [0.5] if dur <= 0 else [0.12, 0.28, 0.44, 0.60, 0.76]
    with tempfile.TemporaryDirectory() as td:
        cands: list[tuple[float, Path]] = []
        for i, frac in enumerate(fractions):
            p = Path(td) / f"cand{i}.jpg"
            if _extract_frame(video_path, dur * frac, p):
                cands.append((_score(p), p))
        if not cands:
            raise RuntimeError("clip se koi frame nahi nikaal paya (ffmpeg)")
        cands.sort(key=lambda x: x[0], reverse=True)
        best = cands[0][1]
        data = best.read_bytes()
        out.write_bytes(data)

    _draw_text(out, text)
    # YouTube custom thumbnail limit: 2MB
    if out.stat().st_size > 2 * 1024 * 1024:
        try:
            from PIL import Image
            img = Image.open(out).convert("RGB")
            img.save(out, "JPEG", quality=72)
        except Exception:
            pass
    return str(out)
