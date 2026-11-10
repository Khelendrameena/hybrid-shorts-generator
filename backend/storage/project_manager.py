"""Project lifecycle + on-disk layout. Originals are NEVER overwritten:
uploads are copied into the project folder; all outputs go to subfolders."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import PROJECTS_DIR, UPLOADS_DIR
from . import database as db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id
    for sub in ("clips", "frames", "renders", "exports"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def create_project(title: str, source_type: str, source_ref: str) -> dict:
    pid = uuid.uuid4().hex[:12]
    db.execute(
        "INSERT INTO projects (id,title,source_type,source_ref,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
        (pid, title, source_type, source_ref, "created", _now(), _now()),
    )
    project_dir(pid)
    return get_project(pid)


def get_project(pid: str) -> dict | None:
    p = db.query_one("SELECT * FROM projects WHERE id=?", (pid,))
    if p:
        p["meta"] = db.loads(p.get("meta"), {})
    return p


def list_projects() -> list[dict]:
    rows = db.query_all("SELECT * FROM projects ORDER BY created_at DESC")
    for r in rows:
        r["meta"] = db.loads(r.get("meta"), {})
    return rows


def update_project(pid: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = db.dumps(fields["meta"])
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE projects SET {cols} WHERE id=?", (*fields.values(), pid))


def save_upload(pid: str, src: Path, filename: str) -> Path:
    dest_dir = project_dir(pid)
    dest = dest_dir / f"source_{Path(filename).name}"
    shutil.copy2(src, dest)  # copy, never move/overwrite the user's original
    update_project(pid, video_path=str(dest))
    return dest


def save_transcript_ref(pid: str, json_path: str, srt_path: str, language: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO transcripts (project_id,json_path,srt_path,language) VALUES (?,?,?,?)",
        (pid, json_path, srt_path, language),
    )


def save_clip(clip: dict) -> None:
    db.execute(
        """INSERT OR REPLACE INTO clips
           (id,project_id,start,end,score,scores,transcript,category,reasons,metadata,status,output_path,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            clip["id"], clip["project_id"], clip["start"], clip["end"], clip.get("score", 0),
            db.dumps(clip.get("scores", {})), clip.get("transcript", ""), clip.get("category", ""),
            db.dumps(clip.get("reasons", [])), db.dumps(clip.get("metadata", {})),
            clip.get("status", "pending"), clip.get("output_path"), _now(),
        ),
    )


def list_clips(pid: str) -> list[dict]:
    rows = db.query_all("SELECT * FROM clips WHERE project_id=? ORDER BY score DESC", (pid,))
    for r in rows:
        r["scores"] = db.loads(r.get("scores"), {})
        r["reasons"] = db.loads(r.get("reasons"), [])
        r["metadata"] = db.loads(r.get("metadata"), {})
    return rows


def update_clip(cid: str, **fields) -> None:
    for k in ("scores", "reasons", "metadata"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = db.dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE clips SET {cols} WHERE id=?", (*fields.values(), cid))
