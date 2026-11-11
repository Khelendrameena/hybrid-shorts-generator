"""FFmpeg rendering: 9:16 vertical 1080x1920 (Shorts/Reels frame), H.264 + AAC,
animated word-highlight subtitles, loudness normalisation, optional silence
trimming and optional background music mix. Never overwrites the source video.

Frame strategy (user fix, 2026-11-10): the output frame is always the full
9:16 Shorts/Reels canvas, but the DEFAULT mode is now "fit" — the ENTIRE
source frame is scaled to fit inside the canvas (nothing is cropped away,
no side content / faces / on-screen text gets cut) and the empty area above
and below is filled with a darkened, blurred copy of the same video, which
is how YouTube Shorts / Reels show landscape videos. The old centre/face
crop is still available as mode="crop" (Settings → Frame mode) for videos
where a full-bleed crop looks better. mode="pad" is kept as an alias of fit.
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


def resolve_mode(mode: str | None) -> str:
    """Normalise the frame mode: 'fit' (default, nothing cut) or 'crop'."""
    m = (mode or getattr(settings, "frame_mode", "fit") or "fit").strip().lower()
    if m in ("fit", "pad", "blur", "blur-pad", "auto"):
        return "fit"
    if m == "crop":
        return "crop"
    return "fit"


def build_video_graph(mode: str | None, W: int, H: int,
                      face_center: tuple[float, float] | None = None,
                      src_w: int | None = None, src_h: int | None = None) -> str:
    """Return the video filter graph (without subtitles) for [0:v] -> [vbase].

    fit : split into a blurred, slightly darkened background scaled to COVER
          the canvas + the full source scaled to fit INSIDE it, overlaid
          centred. The source is never cropped — every pixel of the original
          frame stays visible.
    crop: full-bleed 9:16 crop (face-aware when a face centre is known).
    """
    m = resolve_mode(mode)
    # fps=30 at the end: constant frame rate output. VFR-ish sources make
    # some phone players stall/seek badly; every Shorts/Reels upload is CFR.
    if m == "fit":
        return (f"[0:v]split=2[vinbg][vinfg];"
                f"[vinbg]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},gblur=sigma=32,eq=brightness=-0.07:saturation=0.85[bg];"
                f"[vinfg]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"setsar=1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30[vbase]")
    # crop (opt-in): face-aware window when possible, else centre crop
    if src_w and src_h and face_center:
        crop_w = int(src_h * 9 / 16)
        if crop_w <= src_w:
            cx = int(face_center[0] * src_w)
            x = max(0, min(src_w - crop_w, cx - crop_w // 2))
            return f"[0:v]crop={crop_w}:{src_h}:{x}:0,scale={W}:{H},setsar=1,fps=30[vbase]"
    return f"[0:v]crop=ih*9/16:ih,scale={W}:{H},setsar=1,fps=30[vbase]"


def render_clip(video_path: str | Path, start: float, end: float,
                transcript_segments: list[dict], out_path: str | Path,
                theme: str = "dynamic", face_center: tuple[float, float] | None = None,
                src_w: int | None = None, src_h: int | None = None,
                mode: str | None = None, normalize: bool = True,
                bg_music: str | None = None, progress_cb=None) -> dict:
    if end <= start:
        raise ValueError("Invalid clip timestamps: end must be after start")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    W, H = settings.output_width, settings.output_height
    mode = resolve_mode(mode)

    words = words_for_range(transcript_segments, start, end)
    work = out_path.parent / f".{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / "subs.ass"
    ass_path.write_text(build_ass(words, theme, W, H), encoding="utf-8")
    srt_path = work / "subs.srt"
    srt_path.write_text(build_srt(words), encoding="utf-8")

    # subtitles filter needs an escaped path on Windows too
    ass_esc = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vgraph = build_video_graph(mode, W, H, face_center, src_w, src_h)
    # loudnorm internally UPSAMPLES audio (44.1k source -> 96k output,
    # measured 2026-11-11) — many phone/WhatsApp players stall on 96kHz AAC.
    # Always resample back to the standard 48kHz and reset audio timestamps.
    af = ("loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,asetpts=N/SR/TB" if normalize
          else "aresample=48000,asetpts=N/SR/TB")

    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video_path)]
    if bg_music:
        cmd += ["-stream_loop", "-1", "-i", str(bg_music)]
        fc = (f"{vgraph};[vbase]subtitles='{ass_esc}'[vout];"
              f"[0:a]{af}[voice];[1:a]volume=0.12,aresample=48000[music];"
              f"[voice][music]amix=inputs=2:duration=first,aresample=48000,asetpts=N/SR/TB[aout]")
    else:
        fc = (f"{vgraph};[vbase]subtitles='{ass_esc}'[vout];"
              f"[0:a]{af}[aout]")
    cmd += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]"]
    # Player-friendly encode (user report 2026-11-11: downloaded Shorts
    # "ruk jaati hai / buffer karti hai" on the phone): the old defaults had
    # keyframes every ~8.3s (x264 GOP 250), so players had to decode seconds
    # of video to start/seek — felt exactly like buffering. Now: a keyframe
    # every 2s, capped bitrate spikes, explicit High@4.2 profile.
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.2",
            "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-maxrate", "10M", "-bufsize", "20M",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", str(out_path)]
    if progress_cb:
        progress_cb(10, "Rendering with FFmpeg…")
    _run(cmd)
    if progress_cb:
        progress_cb(100, "Render complete")
    return {"output": str(out_path), "srt": str(srt_path), "ass": str(ass_path),
            "duration": round(end - start, 2), "width": W, "height": H, "mode": mode}


def export_srt_for_clip(transcript_segments: list[dict], start: float, end: float) -> str:
    return build_srt(words_for_range(transcript_segments, start, end))
