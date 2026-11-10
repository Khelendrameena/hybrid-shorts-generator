"""Frame-fit regression tests (user report 2026-11-10): the Shorts/Reels
9:16 output frame stayed, but landscape videos were centre-cropped into it,
so side content was cut off and never visible. Default mode is now "fit":
the whole source frame is shown inside the 9:16 canvas over a blurred
background — nothing is cropped away."""
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.rendering.ffmpeg_engine import build_video_graph, render_clip, resolve_mode

pytestmark_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                       reason="ffmpeg not installed")


def test_resolve_mode_defaults_to_fit():
    assert resolve_mode(None) == "fit"
    assert resolve_mode("pad") == "fit"      # old alias
    assert resolve_mode("auto") == "fit"
    assert resolve_mode("crop") == "crop"
    assert resolve_mode("garbage") == "fit"  # safe default: nothing cut


def test_fit_graph_scales_whole_frame_inside_canvas():
    g = build_video_graph("fit", 1080, 1920)
    # foreground: fit INSIDE the canvas (decrease) — never cropped
    assert "force_original_aspect_ratio=decrease" in g
    # background: blurred cover-fill of the same video
    assert "force_original_aspect_ratio=increase" in g
    assert "gblur" in g
    assert "overlay=(W-w)/2:(H-h)/2" in g


def test_crop_graph_is_full_bleed_crop():
    g = build_video_graph("crop", 1080, 1920, src_w=1280, src_h=720)
    assert "crop=" in g and "gblur" not in g


def _avg_rgb(video: Path, x: int, y: int, t: float = 1.0) -> tuple[int, int, int]:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video),
         "-vf", f"crop=20:20:{x}:{y},scale=1:1", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    assert r.returncode == 0 and len(r.stdout) >= 3, r.stderr.decode()[-400:]
    return r.stdout[0], r.stdout[1], r.stdout[2]


@pytestmark_ffmpeg
def test_fit_render_keeps_all_four_corners_visible(tmp_path):
    """Landscape source with RED boxes in all 4 corners. In fit mode every
    corner must still be visible in the 9:16 output (crop mode cuts the
    left/right corners away entirely)."""
    src = tmp_path / "src.mp4"
    boxes = ",".join([
        "drawbox=x=0:y=0:w=70:h=70:color=red:t=fill",
        "drawbox=x=iw-70:y=0:w=70:h=70:color=red:t=fill",
        "drawbox=x=0:y=ih-70:w=70:h=70:color=red:t=fill",
        "drawbox=x=iw-70:y=ih-70:w=70:h=70:color=red:t=fill",
    ])
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=0x102040:s=1280x720:r=25:d=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-vf", boxes, "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(src)], check=True)

    out = tmp_path / "short.mp4"
    res = render_clip(src, 0.0, 3.0, [], out, mode="fit",
                      src_w=1280, src_h=720)
    assert res["mode"] == "fit" and out.exists()

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True)
    assert probe.stdout.strip() == "1080,1920"

    # Foreground: 1080 wide, ~607 tall, centred -> top edge ~656, bottom ~1263.
    # Sample just inside each foreground corner: all four must be RED.
    for (x, y) in [(10, 666), (1050, 666), (10, 1233), (1050, 1233)]:
        r, g, b = _avg_rgb(out, x, y)
        assert r > 150 and g < 90 and b < 90, f"corner at {(x, y)} not red: {(r, g, b)}"
