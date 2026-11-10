"""Video metadata via ffprobe: duration, resolution, fps, audio/video streams."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe(video_path: str | Path) -> dict:
    p = str(video_path)
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", p,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return {"path": p, "valid": False, "error": (out.stderr or "ffprobe failed")[:500]}
        data = json.loads(out.stdout or "{}")
    except FileNotFoundError:
        return {"path": p, "valid": False, "error": "ffprobe not found — install FFmpeg"}
    except Exception as e:  # corrupted file, timeout, bad json
        return {"path": p, "valid": False, "error": str(e)[:500]}

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fps = None
    if video:
        r = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        try:
            num, den = r.split("/")
            fps = float(num) / float(den) if float(den) else None
        except Exception:
            fps = None
    duration = None
    try:
        duration = float(fmt.get("duration") or (video or {}).get("duration") or 0) or None
    except Exception:
        duration = None
    return {
        "path": p,
        "valid": bool(video) and duration is not None,
        "duration": duration,
        "size_bytes": int(fmt.get("size", 0)) if str(fmt.get("size", "")).isdigit() else None,
        "format": fmt.get("format_name"),
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "fps": fps,
        "video_codec": video.get("codec_name") if video else None,
        "audio_streams": [{"codec": a.get("codec_name"), "channels": a.get("channels"),
                           "language": (a.get("tags") or {}).get("language")} for a in audio],
        "has_audio": len(audio) > 0,
    }
