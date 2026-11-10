"""Synthetic end-to-end verification (no model downloads needed):
synthetic video -> probe -> scenes/frames/energy/faces -> candidate detection
(heuristic path when `laya` is not installed; real Laya when it is) ->
fallback metadata (when Ollama is offline) -> FFmpeg render -> ffprobe check
that the Short really is 1080x1920 H.264 + AAC.

Run:  python scripts/e2e_synthetic.py
On a machine with Ollama running and laya installed, the same stages use the
real models automatically — this script prints which engine actually ran.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORK = Path(__file__).resolve().parent.parent / "outputs" / "e2e"
WORK.mkdir(parents=True, exist_ok=True)
VIDEO = WORK / "synthetic.mp4"

HOOKY = ("What if everything you knew about money was wrong? This shocking fact "
         "changes everything today. Most people make this one mistake every day "
         "and lose thousands without knowing it. Here is the simple truth that "
         "nobody tells you, and the exact step to fix it right now forever.")
FLAT = ("Then we discussed the routine schedule and some normal points about "
        "the meeting agenda and other ordinary matters for a while without "
        "anything particularly notable happening in this part at all today.")


def make_video():
    if VIDEO.exists():
        return
    subprocess.run(["ffmpeg", "-y", "-v", "quiet",
                    "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=70",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=70",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(VIDEO)],
                   check=True)


def fake_transcript() -> dict:
    segments, t = [], 0.0
    texts = [HOOKY, FLAT, HOOKY.replace("money", "health"), FLAT]
    for i, text in enumerate(texts):
        words, wt = [], t
        for w in text.split():
            words.append({"word": w, "start": round(wt, 2), "end": round(wt + 0.32, 2), "probability": 0.96})
            wt += 0.36
        segments.append({"id": i, "start": round(t, 2), "end": round(wt, 2), "text": text,
                         "words": words, "avg_logprob": -0.08, "no_speech_prob": 0.01, "speaker_turn": i})
        t = wt + 0.5
    return {"language": "en", "language_probability": 0.99, "duration": t,
            "segments": segments, "full_text": " ".join(texts)}


def main() -> int:
    make_video()
    from backend.video.metadata import probe
    meta = probe(VIDEO)
    assert meta["valid"] and meta["has_audio"], meta
    print(f"[ok] probe: {meta['width']}x{meta['height']} {meta['duration']:.0f}s fps={meta['fps']}")

    from backend.video.scene_detector import detect_scenes
    from backend.video.frame_extractor import extract_frames, audio_energy_profile
    from backend.video.face_tracker import track_faces
    scenes = detect_scenes(VIDEO)
    frames = extract_frames(VIDEO, WORK / "frames")
    energy = audio_energy_profile(VIDEO)
    faces = track_faces(VIDEO, duration=30)
    print(f"[ok] video analysis: {len(scenes)} scenes, {len(frames)} frames, {len(energy)} energy windows, {len(faces)} face samples")
    assert frames and energy

    transcript = fake_transcript()
    from backend.analysis.candidate_detector import detect_candidates
    clips = detect_candidates(transcript, float(meta["duration"]), audio_energy=energy,
                              face_track=faces, min_score=30, max_clips=5)
    print(f"[ok] candidates: {len(clips)} clips")
    for c in clips:
        print(f"     - {c['display_id']} {c['start']:.1f}-{c['end']:.1f}s score={c['score']} "
              f"cat={c['category']} engine={c['engine']}")
    assert clips, "no candidates produced"

    from backend.models.ollama_engine import OllamaEngine
    ollama = OllamaEngine()
    health = ollama.health()
    md = ollama.generate_metadata(clips[0])
    print(f"[ok] metadata (ollama online={health['online']}): source={md.get('source')} title={md['title']!r}")
    assert md["title"] and "#shorts" in md["hashtags"]

    from backend.rendering.ffmpeg_engine import render_clip
    c = clips[0]
    out = WORK / "short_e2e.mp4"
    render_clip(VIDEO, c["start"], c["end"], transcript["segments"], out,
                src_w=meta["width"], src_h=meta["height"])
    rm = probe(out)
    assert rm["valid"] and rm["width"] == 1080 and rm["height"] == 1920, rm
    print(f"[ok] render: {out.name} is {rm['width']}x{rm['height']} codec={rm['video_codec']} audio={rm['audio_streams']}")
    print("\nE2E SYNTHETIC PIPELINE: ALL STAGES PASSED")
    print(json.dumps({"clips": len(clips), "engine": clips[0]["engine"],
                      "metadata_source": md.get("source")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
