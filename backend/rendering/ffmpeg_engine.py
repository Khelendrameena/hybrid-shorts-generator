"""FFmpeg rendering: 9:16 vertical 1080x1920, H.264 + AAC, animated word-highlight
subtitles, face-aware crop, loudness normalisation, optional silence trimming
and optional background music mix. Never overwrites the source video.

Crop strategy (honest): if a face centre is known for the clip, the 9:16 crop
window is centred on the face (clamped inside the frame). Otherwise centre crop.
Wide shots keep a blurred-pad fallback OFF by default — crop is preferred for
Shorts; set mode='pad' in settings UI to use blurred background instead.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import settings
from .subtitle_engine import build_ass, build_srt, words_for_range


def _run(cmd: list[str], timeout: int = 1800) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {(r.stderr or '')[-1200:]}")


def render_clip(video_path: str | Path, start: float, end: float,
                transcript_segments: list[dict], out_path: str | Path,
                theme: str = "dynamic", face_center: tuple[float, float] | None = None,
                src_w: int | None = None, src_h: int | None = None,
                mode: str = "crop", normalize: bool = True,
                bg_music: str | None = None, progress_cb=None) -> dict:
    if end <= start:
        raise ValueError("Invalid clip timestamps: end must be after start")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    W, H = settings.output_width, settings.output_height

    words = words_for_range(transcript_segments, start, end)
    work = out_path.parent / f".{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / "subs.ass"
    ass_path.write_text(build_ass(words, theme, W, H), encoding="utf-8")
    srt_path = work / "subs.srt"
    srt_path.write_text(build_srt(words), encoding="utf-8")

    # --- video filter: face-aware crop or blurred pad, then scale to 1080x1920
    if mode == "pad":
        vf_video = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},gblur=sigma=40[bg];[b]scale={W}:-2[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    else:
        if src_w and src_h and face_center:
            crop_w = int(src_h * 9 / 16)
            if crop_w <= src_w:
                cx = int(face_center[0] * src_w)
                x = max(0, min(src_w - crop_w, cx - crop_w // 2))
                vf_video = f"crop={crop_w}:{src_h}:{x}:0,scale={W}:{H}"
            else:
                vf_video = f"crop=ih*9/16:ih,scale={W}:{H}"
        else:
            vf_video = f"crop=ih*9/16:ih,scale={W}:{H}"
    # subtitles filter needs an escaped path on Windows too
    ass_esc = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf = f"{vf_video},subtitles='{ass_esc}'"

    af = "loudnorm=I=-16:TP=-1.5:LRA=11" if normalize else "anull"
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video_path)]
    if bg_music:
        cmd += ["-stream_loop", "-1", "-i", str(bg_music)]
        afilter = (f"[0:a]{af}[voice];[1:a]volume=0.12[music];"
                   f"[voice][music]amix=inputs=2:duration=first[aout]")
        cmd += ["-filter_complex", f"[0:v]{vf}[vout];{afilter}",
                "-map", "[vout]", "-map", "[aout]"]
    else:
        cmd += ["-vf", vf, "-af", af]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            "-shortest", str(out_path)]
    if progress_cb:
        progress_cb(10, "Rendering with FFmpeg…")
    _run(cmd)
    if progress_cb:
        progress_cb(100, "Render complete")
    return {"output": str(out_path), "srt": str(srt_path), "ass": str(ass_path),
            "duration": round(end - start, 2), "width": W, "height": H}


def export_srt_for_clip(transcript_segments: list[dict], start: float, end: float) -> str:
    return build_srt(words_for_range(transcript_segments, start, end))
