"""Intelligent frame sampling: 1 frame / 2s by default, denser around scene
changes; black-frame detection; per-frame visual metadata (brightness, sharpness,
motion vs previous frame, face presence — filled by face_tracker)."""
from __future__ import annotations

from pathlib import Path


def extract_frames(video_path: str | Path, out_dir: str | Path,
                   interval: float = 2.0, scene_times: list[float] | None = None,
                   save_frames: bool = False) -> list[dict]:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if fps else 0

    times = set()
    t = 0.0
    while t < duration:
        times.add(round(t, 2))
        t += interval
    for st in (scene_times or []):  # denser sampling around scene changes
        for dt in (-1.0, 0.0, 1.0):
            if 0 <= st + dt < duration:
                times.add(round(st + dt, 2))
    times = sorted(times)

    out_dir = Path(out_dir)
    if save_frames:
        out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    prev_gray = None
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        motion = 0.0
        if prev_gray is not None and prev_gray.shape == gray.shape:
            motion = float(np.abs(gray.astype(float) - prev_gray.astype(float)).mean())
        prev_gray = gray
        is_black = brightness < 12.0
        path = None
        if save_frames:
            p = out_dir / f"frame_{int(t*1000):08d}.jpg"
            cv2.imwrite(str(p), frame)
            path = str(p)
        results.append({
            "time": t, "brightness": round(brightness, 2), "sharpness": round(sharpness, 2),
            "motion": round(motion, 3), "is_black": is_black, "path": path,
            "width": int(frame.shape[1]), "height": int(frame.shape[0]),
        })
    cap.release()
    return results


def audio_energy_profile(video_path: str | Path, window_seconds: float = 1.0) -> list[dict]:
    """Per-second RMS audio energy via ffmpeg → raw PCM. Used for excitement /
    laughter / emphasis detection and silence mapping. Empty list if no audio."""
    import subprocess

    import numpy as np  # type: ignore

    cmd = ["ffmpeg", "-v", "quiet", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
           "-f", "s16le", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
        if proc.returncode != 0 or not proc.stdout:
            return []
    except Exception:
        return []
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(float) / 32768.0
    per = int(16000 * window_seconds)
    out = []
    for i in range(0, len(samples), per):
        chunk = samples[i:i + per]
        if len(chunk) == 0:
            break
        rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
        out.append({"time": round(i / 16000.0, 2), "rms": round(rms, 4), "silent": rms < 0.015})
    return out
