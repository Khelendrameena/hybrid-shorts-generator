"""YouTube download via yt-dlp (only where permitted) + strict URL validation,
plus local-file intake for MP4/MOV/MKV/WebM. Progress callback supported."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..storage.project_manager import project_dir

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
SUPPORTED_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


def validate_youtube_url(url: str) -> bool:
    try:
        u = urlparse((url or "").strip())
        return u.scheme in ("http", "https") and (u.hostname or "") in _YT_HOSTS and bool(u.path or u.query)
    except Exception:
        return False


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "video.mp4"


def download_youtube(url: str, project_id: str, progress_cb=None) -> Path:
    """Raises ValueError on invalid URL, RuntimeError on download failure."""
    if not validate_youtube_url(url):
        raise ValueError("Invalid YouTube URL")
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:
        raise RuntimeError("yt-dlp is not installed — run: pip install yt-dlp") from e

    out_dir = project_dir(project_id)
    out_tmpl = str(out_dir / "source_%(title).80s.%(ext)s")

    def hook(d):
        if progress_cb and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            if total:
                progress_cb(done / total * 100.0, f"Downloading… {done//1048576} MB / {total//1048576} MB")

    opts = {
        # Best single file <=1080p to keep disk/VRAM pipeline light; merge to mp4.
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": out_tmpl,
        "progress_hooks": [hook],
        "noplaylist": True,
        "retries": 3,
        "socket_timeout": 30,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("Could not fetch this video (unavailable/private?)")
        path = Path(ydl.prepare_filename(info))
        if path.suffix != ".mp4":
            path = path.with_suffix(".mp4")
        if not path.exists():
            # merged file naming fallback: find newest source_* in dir
            cands = sorted(out_dir.glob("source_*"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not cands:
                raise RuntimeError("Download finished but output file not found")
            path = cands[0]
    if progress_cb:
        progress_cb(100.0, "Download complete")
    return path


def import_local_file(src_path: str | Path, project_id: str) -> Path:
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    if src.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported format {src.suffix}. Supported: {sorted(SUPPORTED_EXTS)}")
    dest = project_dir(project_id) / f"source_{_safe_name(src.name)}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)  # never move or overwrite the original
    return dest
