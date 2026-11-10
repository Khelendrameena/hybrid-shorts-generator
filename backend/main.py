"""FastAPI entry point. Run:  uvicorn backend.main:app --host 127.0.0.1 --port 8000
(or just use run.bat / run.sh which starts backend + frontend together)."""
from __future__ import annotations

import os

os.environ.setdefault("USE_TF", "0")  # before any transformers import (Laya)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .jobs.recovery import mark_interrupted_jobs
from .storage.database import init_db

app = FastAPI(title="Hybrid AI YouTube Shorts Generator",
              description="Laya (decisions) + Ollama qwen3:4b (creative) — 100% local, no paid APIs.",
              version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

init_db()  # at import too, so TestClient / serverless imports work identically


@app.on_event("startup")
def _startup():
    init_db()
    mark_interrupted_jobs()


@app.get("/")
def root():
    return {"app": "Hybrid AI YouTube Shorts Generator", "docs": "/docs",
            "health": "/api/health"}
