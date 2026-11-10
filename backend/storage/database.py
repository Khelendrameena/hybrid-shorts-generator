"""SQLite storage for projects, jobs and clips. Stdlib sqlite3 only."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, title TEXT, source_type TEXT, source_ref TEXT,
  video_path TEXT, duration REAL, status TEXT DEFAULT 'created',
  language TEXT, created_at TEXT, updated_at TEXT, meta TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, project_id TEXT, stage TEXT DEFAULT 'queued',
  progress REAL DEFAULT 0, message TEXT DEFAULT '', error TEXT,
  cancel_requested INTEGER DEFAULT 0, checkpoint TEXT DEFAULT '{}',
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY, project_id TEXT, start REAL, end REAL,
  score REAL, scores TEXT DEFAULT '{}', transcript TEXT DEFAULT '',
  category TEXT DEFAULT '', reasons TEXT DEFAULT '[]',
  metadata TEXT DEFAULT '{}', status TEXT DEFAULT 'pending',
  output_path TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS transcripts (
  project_id TEXT PRIMARY KEY, json_path TEXT, srt_path TEXT, language TEXT
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, connect() as c:
        c.executescript(SCHEMA)


def execute(sql: str, params: tuple = ()) -> None:
    with _lock, connect() as c:
        c.execute(sql, params)
        c.commit()


def query_one(sql: str, params: tuple = ()):
    with connect() as c:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(s, default=None):
    try:
        return json.loads(s) if s else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}
