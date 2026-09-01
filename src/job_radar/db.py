from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, company TEXT NOT NULL, title TEXT NOT NULL,
  location TEXT NOT NULL, workplace TEXT, description TEXT NOT NULL,
  source_url TEXT, experience_min INTEGER, experience_evidence TEXT,
  benefits TEXT NOT NULL DEFAULT '[]', score INTEGER NOT NULL,
  score_breakdown TEXT NOT NULL, why TEXT NOT NULL, concerns TEXT NOT NULL,
  content_hash TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS human_state (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id), status TEXT NOT NULL DEFAULT 'Inbox',
  notes TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, kind TEXT NOT NULL,
  detail TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL, added INTEGER NOT NULL, updated INTEGER NOT NULL,
  unchanged INTEGER NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


@contextmanager
def transaction(db: sqlite3.Connection):
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def content_hash(job: dict) -> str:
    stable = {k: job.get(k) for k in ("company", "title", "location", "description", "source_url")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
