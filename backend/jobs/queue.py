"""The processing pipeline — one job, staged, checkpointed, cancellable.

Stage order enforces the VRAM rule on a 4GB RTX 3050:
  Whisper (GPU) → unload → video analysis (CPU/OpenCV) → Laya (GPU/CPU) →
  unload → Ollama qwen3:4b (GPU, keep_alive=0) → FFmpeg renders (CPU/GPU enc).
Heavy models are never resident together (see models/manager.py).
"""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

from ..config import settings
from ..storage import project_manager as pm
from . import progress


def _cb(job_id: str, stage: str):
    def cb(pct: float, msg: str = ""):
        if progress.is_cancelled(job_id):
            raise InterruptedError("Cancelled by user")
        progress.update_job(job_id, stage=stage, progress=pct, message=msg)
    return cb


def run_pipeline(job_id: str, project_id: str, opts: dict | None = None) -> None:
    opts = opts or {}
    project = pm.get_project(project_id)
    if not project:
        progress.update_job(job_id, stage="failed", error="Project not found")
        return
    pdir = pm.project_dir(project_id)
    job = progress.get_job(job_id) or {}
    ckpt: dict = job.get("checkpoint") or {}

    try:
        # ---- source ------------------------------------------------------
        video_path = project.get("video_path")
        if project["source_type"] == "youtube" and not video_path:
            progress.update_job(job_id, stage="downloading", progress=0, message="Downloading from YouTube…")
            from ..video.downloader import download_youtube

            video_path = str(download_youtube(project["source_ref"], project_id,
                                              progress_cb=_cb(job_id, "downloading")))
            pm.update_project(project_id, video_path=video_path)
        if not video_path or not Path(video_path).exists():
            raise RuntimeError("Source video missing — upload a file or provide a YouTube URL")

        # ---- probe ---------------------------------------------------------
        progress.update_job(job_id, stage="probing", progress=2, message="Reading video metadata…")
        from ..video.metadata import probe

        meta = probe(video_path)
        if not meta.get("valid"):
            raise RuntimeError(f"Invalid/corrupted video: {meta.get('error') or 'no video stream'}")
        if not meta.get("has_audio"):
            raise RuntimeError("Video has no audio stream — nothing to transcribe")
        duration = float(meta["duration"])
        pm.update_project(project_id, duration=duration, status="processing",
                          meta={**(project.get("meta") or {}), "video": meta})

        # ---- transcribe (checkpointed) -------------------------------------
        transcript = None
        tpath = pdir / "transcript.json"
        if ckpt.get("transcript_done") and tpath.exists():
            transcript = json.loads(tpath.read_text(encoding="utf-8"))
            progress.update_job(job_id, stage="transcribing", progress=100, message="Transcript restored from checkpoint")
        else:
            progress.update_job(job_id, stage="transcribing", progress=0, message="Transcribing with Faster-Whisper…")
            from ..transcription.whisper_engine import WhisperEngine

            transcript = WhisperEngine().transcribe(
                video_path, pdir, language=opts.get("language") or settings.default_language,
                progress_cb=_cb(job_id, "transcribing"))
            pm.save_transcript_ref(project_id, str(tpath), str(pdir / "transcript.srt"), transcript["language"])
            pm.update_project(project_id, language=transcript["language"])
            progress.update_job(job_id, checkpoint={"transcript_done": True})

        # ---- video understanding -------------------------------------------
        analysis_path = pdir / "analysis.json"
        if ckpt.get("analysis_done") and analysis_path.exists():
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        else:
            progress.update_job(job_id, stage="analysing_video", progress=5, message="Detecting scenes, faces, audio energy…")
            from ..video.face_tracker import track_faces
            from ..video.frame_extractor import audio_energy_profile, extract_frames
            from ..video.scene_detector import detect_scenes

            scenes = detect_scenes(video_path)
            frames = extract_frames(video_path, pdir / "frames",
                                    scene_times=[s["start"] for s in scenes])
            energy = audio_energy_profile(video_path)
            faces = track_faces(video_path, duration=duration)
            analysis = {"scenes": scenes, "frames": frames, "audio_energy": energy, "face_track": faces}
            analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
            progress.update_job(job_id, checkpoint={"analysis_done": True},
                                stage="analysing_video", progress=100,
                                message=f"{len(scenes)} scenes, {len(frames)} frames analysed")

        # ---- Laya candidates (checkpointed) ---------------------------------
        clips_path = pdir / "candidates.json"
        clips: list[dict] = []
        if ckpt.get("candidates_done") and clips_path.exists():
            clips = json.loads(clips_path.read_text(encoding="utf-8"))
        else:
            progress.update_job(job_id, stage="laya_analysis", progress=0, message="Laya is scoring candidate moments…")
            from ..analysis.candidate_detector import detect_candidates
            from ..models.laya_engine import LayaEngine

            laya = LayaEngine()
            clips = detect_candidates(
                transcript, duration, audio_energy=analysis.get("audio_energy"),
                face_track=analysis.get("face_track"), laya=laya,
                progress_cb=_cb(job_id, "laya_analysis"),
                max_clips=opts.get("max_clips"), min_score=opts.get("min_score"))
            laya.unload()
            for c in clips:
                c["project_id"] = project_id
                c["status"] = "pending"
                pm.save_clip(c)
            clips_path.write_text(json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8")
            progress.update_job(job_id, checkpoint={"candidates_done": True},
                                stage="laya_analysis", progress=100,
                                message=f"{len(clips)} clips selected")

        # ---- Ollama metadata --------------------------------------------------
        if not ckpt.get("metadata_done"):
            progress.update_job(job_id, stage="ollama_generation", progress=0, message="Ollama is writing titles & hooks…")
            from ..models.ollama_engine import OllamaEngine

            ollama = OllamaEngine(model=opts.get("ollama_model") or settings.ollama_model)
            total = max(1, len(clips))
            for i, c in enumerate(clips):
                if progress.is_cancelled(job_id):
                    raise InterruptedError("Cancelled by user")
                md = ollama.generate_metadata(c, language=opts.get("language") or settings.default_language)
                c["metadata"] = md
                pm.update_clip(c["id"], metadata=md)
                progress.update_job(job_id, stage="ollama_generation",
                                    progress=(i + 1) / total * 100.0,
                                    message=f"Metadata {i + 1}/{total}")
            ollama.unload()
            clips_path.write_text(json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8")
            progress.update_job(job_id, checkpoint={"metadata_done": True})

        pm.update_project(project_id, status="ready")
        progress.update_job(job_id, stage="done", progress=100,
                            message=f"Done — {len(clips)} Shorts ready in the Editor")
    except InterruptedError:
        progress.update_job(job_id, stage="cancelled", message="Cancelled — progress checkpointed, Resume anytime")
        pm.update_project(project_id, status="created")
    except Exception as e:
        traceback.print_exc()
        progress.update_job(job_id, stage="failed", error=str(e)[:800])
        pm.update_project(project_id, status="failed")


def start_job(project_id: str, opts: dict | None = None) -> dict:
    job = progress.create_job(project_id)
    t = threading.Thread(target=run_pipeline, args=(job["id"], project_id, opts), daemon=True)
    t.start()
    return job


def render_all_approved(job_id: str, project_id: str) -> None:
    """Render stage for approved clips (separate job action from the Editor)."""
    from ..rendering.ffmpeg_engine import render_clip
    from ..transcription.whisper_engine import load_transcript
    from ..video.face_tracker import dominant_face_center

    project = pm.get_project(project_id)
    pdir = pm.project_dir(project_id)
    transcript = load_transcript(pdir) or {"segments": []}
    analysis_path = pdir / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else {}
    vmeta = (project.get("meta") or {}).get("video", {})
    clips = [c for c in pm.list_clips(project_id) if c["status"] in ("approved", "rendered")]
    total = max(1, len(clips))
    try:
        for i, c in enumerate(clips):
            if progress.is_cancelled(job_id):
                raise InterruptedError("Cancelled by user")
            cx, cy, _ = dominant_face_center(analysis.get("face_track") or [], c["start"], c["end"])
            out = pdir / "renders" / f"{c.get('display_id') or c['id']}.mp4"
            theme = (c.get("metadata") or {}).get("caption_style") or settings.subtitle_theme
            render_clip(project["video_path"], c["start"], c["end"], transcript["segments"],
                        out, theme=theme, face_center=(cx, cy),
                        src_w=vmeta.get("width"), src_h=vmeta.get("height"))
            pm.update_clip(c["id"], status="rendered", output_path=str(out))
            progress.update_job(job_id, stage="rendering", progress=(i + 1) / total * 100.0,
                                message=f"Rendered {i + 1}/{total}")
        progress.update_job(job_id, stage="done", progress=100, message="All approved Shorts rendered")
    except InterruptedError:
        progress.update_job(job_id, stage="cancelled", message="Render cancelled")
    except Exception as e:
        progress.update_job(job_id, stage="failed", error=str(e)[:800])
