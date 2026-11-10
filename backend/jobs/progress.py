"""Job progress: persisted in SQLite so the Processing page can poll and a
restarted server can show exactly where a job stopped."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..storage import database as db

STAGES = ["queued", "downloading", "probing", "transcribing", "analysing_video",
          "laya_analysis", "ollama_generation", "rendering", "done", "failed", "cancelled"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_job(project_id: str) -> dict:
    jid = uuid.uuid4().hex[:12]
    db.execute("INSERT INTO jobs (id,project_id,stage,created_at,updated_at) VALUES (?,?,?,?,?)",
               (jid, project_id, "queued", _now(), _now()))
    return get_job(jid)


def get_job(jid: str) -> dict | None:
    j = db.query_one("SELECT * FROM jobs WHERE id=?", (jid,))
    if j:
        j["checkpoint"] = db.loads(j.get("checkpoint"), {})
        j["cancel_requested"] = bool(j.get("cancel_requested"))
    return j


def latest_job(project_id: str) -> dict | None:
    j = db.query_one("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,))
    if j:
        j["checkpoint"] = db.loads(j.get("checkpoint"), {})
        j["cancel_requested"] = bool(j.get("cancel_requested"))
    return j


def update_job(jid: str, stage: str | None = None, progress: float | None = None,
               message: str | None = None, error: str | None = None,
               checkpoint: dict | None = None) -> None:
    cur = get_job(jid) or {}
    fields: dict = {"updated_at": _now()}
    if stage is not None:
        fields["stage"] = stage
    if progress is not None:
        fields["progress"] = max(0.0, min(100.0, float(progress)))
    if message is not None:
        fields["message"] = message
    if error is not None:
        fields["error"] = error
    if checkpoint is not None:
        merged = {**(cur.get("checkpoint") or {}), **checkpoint}
        fields["checkpoint"] = db.dumps(merged)
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), jid))


def request_cancel(jid: str) -> None:
    db.execute("UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=?", (_now(), jid))


def is_cancelled(jid: str) -> bool:
    j = get_job(jid)
    return bool(j and j.get("cancel_requested"))
