"""Resume support: a job checkpoints after every expensive stage
(transcript saved → skip transcription; candidates saved → skip Laya;
metadata saved → skip Ollama). On startup, jobs left mid-flight are marked
'failed' with a resumable flag — the user hits Resume and the pipeline picks
up from the last checkpoint instead of starting over."""
from __future__ import annotations

from . import progress


def mark_interrupted_jobs() -> int:
    from ..storage import database as db

    rows = db.query_all(
        "SELECT id FROM jobs WHERE stage NOT IN ('done','failed','cancelled','queued')")
    for r in rows:
        progress.update_job(r["id"], stage="failed",
                            error="Interrupted (server restart). Use Resume — completed stages are checkpointed and will be skipped.")
    return len(rows)


def resumable_stages(checkpoint: dict) -> list[str]:
    done = []
    if checkpoint.get("transcript_done"):
        done.append("transcribing")
    if checkpoint.get("analysis_done"):
        done.append("analysing_video")
    if checkpoint.get("candidates_done"):
        done.append("laya_analysis")
    if checkpoint.get("metadata_done"):
        done.append("ollama_generation")
    return done
