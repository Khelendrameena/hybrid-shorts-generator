"""REST API for the dashboard. All long work runs as background jobs;
these endpoints start/poll/cancel them and serve editor + export data."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..jobs import progress, queue
from ..storage import project_manager as pm

router = APIRouter(prefix="/api")


class YouTubeIn(BaseModel):
    url: str
    title: str | None = None


class ProcessIn(BaseModel):
    max_clips: int | None = None
    min_score: float | None = None
    language: str | None = None
    ollama_model: str | None = None


class ClipPatch(BaseModel):
    start: float | None = None
    end: float | None = None
    status: str | None = None
    metadata: dict | None = None


class SettingsIn(BaseModel):
    ollama_model: str | None = None
    ollama_url: str | None = None
    laya_model_id: str | None = None
    whisper_model: str | None = None
    max_clips: int | None = None
    min_score: float | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    subtitle_theme: str | None = None
    frame_mode: str | None = None
    transcript_source: str | None = None
    caption_language: str | None = None
    language: str | None = None


@router.get("/health")
def health():
    from ..models.laya_engine import LayaEngine
    from ..models.manager import model_manager
    from ..models.ollama_engine import OllamaEngine

    laya_ok, laya_msg = LayaEngine().available()
    return {"ok": True, "laya": {"installed": laya_ok, "note": laya_msg,
                                 "model": settings.laya_model_id},
            "ollama": OllamaEngine().health(), "usage": model_manager.usage(),
            "ollama_model": settings.ollama_model}


@router.get("/settings")
def get_settings():
    return settings.as_dict()


@router.post("/settings")
def update_settings(body: SettingsIn):
    # Runtime settings (persisted by the frontend in localStorage too; here we
    # update the live process so the next job uses them immediately).
    if body.ollama_model:
        settings.ollama_model = body.ollama_model
    if body.ollama_url:
        settings.ollama_url = body.ollama_url.rstrip("/")
    if body.laya_model_id:
        settings.laya_model_id = body.laya_model_id
    if body.whisper_model:
        settings.whisper_model = body.whisper_model
    if body.max_clips:
        settings.max_clips = body.max_clips
    if body.min_score is not None:
        settings.min_clip_score = body.min_score
    if body.min_duration:
        settings.min_clip_duration = body.min_duration
    if body.max_duration:
        settings.max_clip_duration = body.max_duration
    if body.subtitle_theme:
        settings.subtitle_theme = body.subtitle_theme
    if body.frame_mode:
        from ..rendering.ffmpeg_engine import resolve_mode
        settings.frame_mode = resolve_mode(body.frame_mode)
    if body.transcript_source in ("auto", "whisper"):
        settings.transcript_source = body.transcript_source
    if body.caption_language in ("auto", "hindi", "english", "hinglish"):
        settings.caption_language = body.caption_language
    if body.language:
        settings.default_language = body.language
    return settings.as_dict()


@router.get("/projects")
def projects():
    return pm.list_projects()


@router.post("/projects/youtube")
def create_youtube(body: YouTubeIn):
    from ..video.downloader import validate_youtube_url

    if not validate_youtube_url(body.url):
        raise HTTPException(400, "Invalid YouTube URL")
    return pm.create_project(body.title or "YouTube video", "youtube", body.url.strip())


@router.post("/projects/upload")
async def create_upload(file: UploadFile = File(...), title: str = Form(default="")):
    from ..video.downloader import SUPPORTED_EXTS

    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise HTTPException(400, f"Unsupported format {ext}. Use MP4, MOV, MKV or WebM.")
    project = pm.create_project(title or (file.filename or "Uploaded video"), "upload", file.filename or "")
    dest = pm.project_dir(project["id"]) / f"source_{Path(file.filename).name}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    pm.update_project(project["id"], video_path=str(dest))
    return pm.get_project(project["id"])


@router.get("/projects/{pid}")
def get_project(pid: str):
    p = pm.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    job = progress.latest_job(pid)
    return {**p, "job": job, "clips": pm.list_clips(pid)}


@router.post("/projects/{pid}/process")
def process_project(pid: str, body: ProcessIn | None = None):
    if not pm.get_project(pid):
        raise HTTPException(404, "Project not found")
    opts = body.model_dump(exclude_none=True) if body else {}
    return queue.start_job(pid, opts)


@router.post("/projects/{pid}/resume")
def resume_project(pid: str):
    """Resume = start a new job; the pipeline skips checkpointed stages."""
    if not pm.get_project(pid):
        raise HTTPException(404, "Project not found")
    prev = progress.latest_job(pid)
    job = queue.start_job(pid)
    if prev:
        # carry checkpoints forward so completed stages are skipped
        progress.update_job(job["id"], checkpoint=prev.get("checkpoint") or {})
        job = progress.get_job(job["id"])
    return job


@router.post("/jobs/{jid}/cancel")
def cancel_job(jid: str):
    progress.request_cancel(jid)
    return {"ok": True}


@router.get("/jobs/{jid}")
def get_job(jid: str):
    j = progress.get_job(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return j


@router.get("/projects/{pid}/transcript")
def get_transcript(pid: str):
    from ..transcription.whisper_engine import load_transcript

    t = load_transcript(pm.project_dir(pid))
    if not t:
        raise HTTPException(404, "No transcript yet")
    return t


@router.get("/projects/{pid}/analysis")
def get_analysis(pid: str):
    p = pm.project_dir(pid) / "analysis.json"
    cand = pm.project_dir(pid) / "candidates.json"
    return {"analysis": json.loads(p.read_text(encoding="utf-8")) if p.exists() else None,
            "candidates": json.loads(cand.read_text(encoding="utf-8")) if cand.exists() else []}


@router.patch("/clips/{cid}")
def patch_clip(cid: str, body: ClipPatch):
    fields = body.model_dump(exclude_none=True)
    if fields.get("start") is not None and fields.get("end") is not None and fields["end"] <= fields["start"]:
        raise HTTPException(400, "End must be after start")
    if fields.get("status") is not None and fields["status"] not in ("pending", "approved", "rejected", "rendered"):
        raise HTTPException(400, "Invalid status")
    if not fields:
        raise HTTPException(400, "Nothing to update")
    pm.update_clip(cid, **fields)
    return {"ok": True}


@router.post("/clips/{cid}/regenerate")
def regenerate_clip(cid: str):
    from ..models.ollama_engine import OllamaEngine
    from ..storage import database as db

    row = db.query_one("SELECT * FROM clips WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "Clip not found")
    clip = {"id": cid, "transcript": row["transcript"], "category": row["category"], "score": row["score"]}
    from ..generation.caption_translator import metadata_language

    md = OllamaEngine().generate_metadata(
        clip, language=metadata_language(settings.caption_language) or settings.default_language)
    pm.update_clip(cid, metadata=md)
    return md


_VIRAL_TAGS = ["shorts", "ytshorts", "viral shorts", "trending shorts",
               "short video"]
_VIRAL_HASHTAGS = ["shorts", "viral", "trending", "ytshorts", "shortvideo"]


def _shorts_package(row, md) -> tuple[str, str, list[str]]:
    """Ek Short ka pura upload package: title, description, tags.

    YouTube ke rules dhyaan me rakh kar:
    - Description me 15 se zyada hashtags hon to YouTube SAARI hashtags
      ignore kar deta hai — isliye hashtags cap 12 rakhe hain.
    - Tags ki total limit 500 characters — package ~480 par roka hai.
    - Pehli line hook hoti hai (wahi dikhta hai, wahi rokta hai)."""
    title = (md.get("title") or "Short").strip()
    hook = (md.get("opening_hook") or "").strip()
    body = (md.get("description") or "").strip()

    own_tags: list[str] = []
    for t in md.get("hashtags") or []:
        t = str(t).strip().lstrip("#").strip()
        if t and t.lower() not in [x.lower() for x in own_tags]:
            own_tags.append(t)
    cat = (row.get("category") or "").strip()
    tags: list[str] = []
    for t in own_tags + ([cat] if cat else []) + _VIRAL_TAGS:
        if t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    while sum(len(t) + 1 for t in tags) > 480 and len(tags) > 3:
        tags.pop()

    hashtags: list[str] = []
    # #shorts sabse pehle (sabse zaruri), phir clip ke apne, phir
    # viral wale — taaki cap lagne par bhi zaruri wale na katen.
    for t in ["shorts"] + own_tags + _VIRAL_HASHTAGS:
        h = "#" + t.replace(" ", "")
        if h.lower() not in [x.lower() for x in hashtags]:
            hashtags.append(h)
    hashtags = hashtags[:12]

    parts: list[str] = []
    if hook:
        parts.append(hook)
    if body and body.lower() != hook.lower():
        parts.append(body)
    proj = pm.get_project(row["project_id"]) or {}
    if proj.get("source_type") == "youtube" and proj.get("source_ref"):
        parts.append(f"🎬 Full video yahan dekho: {proj['source_ref']}")
    parts.append(" ".join(hashtags))
    return title, "\n\n".join(parts), tags


@router.post("/clips/{cid}/upload")
def upload_clip(cid: str):
    """Manual YouTube upload — sirf Editor ke ⬆ button se chalti hai.
    Upload kahin bhi AUTO nahi hota (na render ke baad, na schedule par):
    user jis clip ka button dabayega, sirf wahi clip jayegi."""
    import time as _time

    from ..storage import database as db
    from ..upload.youtube import is_configured, upload_video

    row = db.query_one("SELECT * FROM clips WHERE id=?", (cid,))
    if not row:
        raise HTTPException(404, "Clip not found")
    if not row.get("output_path") or not Path(row["output_path"]).exists():
        raise HTTPException(400, "Pehle is clip ko render karo — rendered file nahi mili")
    # Shorts format ki pakki check: YouTube ke paas alag "Shorts upload"
    # hota hi nahi — wahi normal upload hai, aur YouTube khud decide
    # karta hai: vertical (9:16) + 3 minute se chhoti video = Short,
    # warna normal Video. Galat format yahin rok do, taaki koi clip
    # galti se normal video na ban jaye.
    from ..video.metadata import probe
    info = probe(row["output_path"])
    if info.get("valid"):
        _w = info.get("width") or 0
        _h = info.get("height") or 0
        _dur = info.get("duration") or 0
        if _h < _w:
            raise HTTPException(
                400, f"Ye clip vertical nahi hai ({_w}x{_h}) — Shorts ke "
                     "liye 9:16 vertical render chahiye")
        if _dur > 180:
            raise HTTPException(
                400, f"Ye clip {_dur:.0f} second lambi hai — 3 minute "
                     "(180s) se lambi video Shorts nahi banti. Editor me "
                     "End time kam karke dobara render karo")
    md = db.loads(row.get("metadata"), {})
    up = md.get("upload") or {}

    def _thumbnail(vid: str) -> tuple[str, str]:
        """Best frame chun kar custom thumbnail lagao. Fail ho to
        upload fail NAHI hota — sirf wajah report hoti hai."""
        try:
            from ..upload.thumbnail import pick_thumbnail
            from ..upload.youtube import set_thumbnail
            tdir = pm.project_dir(row["project_id"]) / "thumbnails"
            img = pick_thumbnail(row["output_path"], tdir / f"{cid}.jpg",
                                 text=md.get("thumbnail_text") or "")
            set_thumbnail(vid, img)
            return "set", ""
        except Exception as exc:
            return "failed", str(exc)[:200]

    if up.get("status") == "uploaded" and up.get("youtube_url"):
        # Pehle se uploaded clip — sirf thumbnail bacha ho to wahi lagao.
        if up.get("thumbnail") == "set":
            return {"youtube_url": up["youtube_url"], "already": True,
                    "thumbnail": "set"}
        if not is_configured():
            return {"youtube_url": up["youtube_url"], "already": True,
                    "thumbnail": "failed",
                    "thumbnail_error": "YouTube connect nahi hai"}
        from ..upload.youtube import video_id_from_url
        st, err = _thumbnail(video_id_from_url(up["youtube_url"]))
        up["thumbnail"] = st
        if err:
            up["thumbnail_error"] = err
        md["upload"] = up
        pm.update_clip(cid, metadata=md)
        return {"youtube_url": up["youtube_url"], "already": True,
                "thumbnail": st, "thumbnail_error": err}

    if not is_configured():
        raise HTTPException(
            400, "YouTube connect nahi hai — pehle terminal me "
                 "scripts/youtube_auth.py chalao (one-time setup)")
    title, description, tags = _shorts_package(row, md)
    try:
        url = upload_video(row["output_path"], title, description,
                           tags=tags, privacy_status="public")
    except Exception as exc:
        raise HTTPException(502, f"YouTube upload fail hua: {exc}")
    from ..upload.youtube import video_id_from_url
    st, err = _thumbnail(video_id_from_url(url))
    md["upload"] = {"status": "uploaded", "youtube_url": url,
                    "uploaded_at": _time.time(), "thumbnail": st,
                    **({"thumbnail_error": err} if err else {})}
    pm.update_clip(cid, metadata=md)
    return {"youtube_url": url, "thumbnail": st, "thumbnail_error": err}


@router.post("/projects/{pid}/render")
def render_project(pid: str):
    import threading

    if not pm.get_project(pid):
        raise HTTPException(404, "Project not found")
    job = progress.create_job(pid)
    approved = [c for c in pm.list_clips(pid) if c["status"] in ("approved", "rendered")]
    if not approved:
        # Old behaviour silently reported "done" with zero renders — the user
        # saw "render ho gaya" but no file existed anywhere. Fail loudly.
        progress.update_job(
            job["id"], stage="failed",
            error="Koi approved clip nahi hai — pehle Editor me clip ko ✓ Approve karo, phir Render dabao.")
        return progress.get_job(job["id"]) or job
    progress.update_job(job["id"], stage="rendering", progress=0,
                        message=f"Rendering {len(approved)} approved Short(s)…")
    threading.Thread(target=queue.render_all_approved, args=(job["id"], pid), daemon=True).start()
    return job


@router.get("/projects/{pid}/clips/{cid}/download")
def download_clip(pid: str, cid: str):
    from ..storage import database as db

    row = db.query_one("SELECT * FROM clips WHERE id=? AND project_id=?", (cid, pid))
    if not row or not row.get("output_path") or not Path(row["output_path"]).exists():
        raise HTTPException(404, "Rendered file not found — render the clip first")
    return FileResponse(row["output_path"], media_type="video/mp4",
                        filename=Path(row["output_path"]).name)


@router.get("/projects/{pid}/export.zip")
def export_zip(pid: str):
    p = pm.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    pdir = pm.project_dir(pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (pdir / "renders").glob("*.mp4"):
            z.write(f, f"shorts/{f.name}")
        clips = pm.list_clips(pid)
        z.writestr("metadata.json", json.dumps(clips, ensure_ascii=False, indent=2))
        from ..rendering.ffmpeg_engine import export_srt_for_clip
        from ..transcription.whisper_engine import load_transcript

        t = load_transcript(pdir)
        if t:
            # Caption language चुनी गई हो और उसका translation cache मौजूद हो
            # तो SRT भी उसी भाषा में — वरना original transcript.
            _segs = t["segments"]
            _cap = (settings.caption_language or "auto").strip().lower()
            _cache = pdir / f"captions_{_cap}.json"
            if _cap != "auto" and _cache.exists():
                _segs = json.loads(_cache.read_text(encoding="utf-8"))
            for c in clips:
                z.writestr(f"srt/{c.get('display_id') or c['id']}.srt",
                           export_srt_for_clip(_segs, c["start"], c["end"]))
            z.write(pdir / "transcript.srt", "transcript.srt")
            z.write(pdir / "transcript.json", "transcript.json")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{pid}-shorts.zip"'})


@router.get("/projects/{pid}/transcript.srt", response_class=PlainTextResponse)
def transcript_srt(pid: str):
    p = pm.project_dir(pid) / "transcript.srt"
    if not p.exists():
        raise HTTPException(404, "No transcript yet")
    return p.read_text(encoding="utf-8")
