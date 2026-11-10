"""Scene transition detection: PySceneDetect (ContentDetector) with an FFmpeg
`select='gt(scene,...)'` fallback when scenedetect is not installed."""
from __future__ import annotations

import subprocess
from pathlib import Path


def detect_scenes(video_path: str | Path, threshold: float = 27.0) -> list[dict]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video  # type: ignore

        video = open_video(str(video_path))
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=threshold))
        sm.detect_scenes(video, show_progress=False)
        scenes = []
        for start, end in sm.get_scene_list():
            scenes.append({"start": round(start.get_seconds(), 3), "end": round(end.get_seconds(), 3)})
        if scenes:
            return scenes
    except Exception:
        pass
    # Fallback: ffmpeg scene filter
    times: list[float] = []
    cmd = ["ffmpeg", "-i", str(video_path), "-filter:v", "select='gt(scene,0.4)',showinfo",
           "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        import re

        for m in re.finditer(r"pts_time:([0-9.]+)", r.stderr or ""):
            times.append(round(float(m.group(1)), 3))
    except Exception:
        return []
    scenes = []
    bounds = [0.0] + sorted(set(times))
    for i, s in enumerate(bounds):
        e = bounds[i + 1] if i + 1 < len(bounds) else s + 5.0
        scenes.append({"start": s, "end": round(e, 3)})
    return scenes
