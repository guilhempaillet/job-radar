from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL DEFAULT '',
  primary_source_id TEXT NOT NULL DEFAULT 'legacy',
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT NOT NULL,
  workplace TEXT,
  workplace_evidence TEXT NOT NULL DEFAULT '[]',
  description TEXT NOT NULL,
  source_url TEXT,
  experience_min INTEGER,
  experience_evidence TEXT NOT NULL DEFAULT '[]',
  compensation_min INTEGER,
  compensation_max INTEGER,
  compensation_currency TEXT,
  compensation_period TEXT,
  compensation_evidence TEXT,
  benefits TEXT NOT NULL DEFAULT '[]',
  benefits_evidence TEXT NOT NULL DEFAULT '[]',
  score INTEGER NOT NULL,
  score_breakdown TEXT NOT NULL,
  why TEXT NOT NULL,
  concerns TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(active, score DESC);

CREATE TABLE IF NOT EXISTS job_sources (
  source_id TEXT NOT NULL,
  source_job_id TEXT NOT NULL,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source_url TEXT,
  raw_hash TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(source_id, source_job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_sources_job ON job_sources(job_id, active);

CREATE TABLE IF NOT EXISTS human_state (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'Inbox',
  notes TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  company TEXT NOT NULL,
  label TEXT NOT NULL,
  last_status TEXT NOT NULL DEFAULT 'never_run',
  last_error TEXT,
  last_attempt_at TEXT,
  last_success_at TEXT,
  current_jobs INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL,
  added INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0,
  unchanged INTEGER NOT NULL DEFAULT 0,
  deduplicated INTEGER NOT NULL DEFAULT 0,
  deactivated INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER REFERENCES runs(id),
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL,
  changed_fields TEXT NOT NULL DEFAULT '[]',
  observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_observed ON changes(observed_at DESC);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    _migrate_legacy_schema(db)
    return db


def _migrate_legacy_schema(db: sqlite3.Connection) -> None:
    """Add post-0.1 columns so an early demo database remains usable."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    additions = {
        "dedupe_key": "TEXT NOT NULL DEFAULT ''",
        "primary_source_id": "TEXT NOT NULL DEFAULT 'legacy'",
        "workplace_evidence": "TEXT NOT NULL DEFAULT '[]'",
        "compensation_min": "INTEGER",
        "compensation_max": "INTEGER",
        "compensation_currency": "TEXT",
        "compensation_period": "TEXT",
        "compensation_evidence": "TEXT",
        "benefits_evidence": "TEXT NOT NULL DEFAULT '[]'",
    }
    for name, definition in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
    table_additions = {
        "runs": {
            "source_id": "TEXT NOT NULL DEFAULT 'legacy'",
            "status": "TEXT NOT NULL DEFAULT 'success'",
            "deduplicated": "INTEGER NOT NULL DEFAULT 0",
            "deactivated": "INTEGER NOT NULL DEFAULT 0",
            "error": "TEXT",
        },
        "changes": {
            "run_id": "INTEGER",
            "source_id": "TEXT NOT NULL DEFAULT 'legacy'",
            "changed_fields": "TEXT NOT NULL DEFAULT '[]'",
        },
    }
    for table, definitions in table_additions.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in definitions.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe_key "
        "ON jobs(dedupe_key) WHERE dedupe_key != ''"
    )
    db.commit()


@contextmanager
def transaction(db: sqlite3.Connection):
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def content_hash(job: dict) -> str:
    stable = {
        key: job.get(key) for key in ("company", "title", "location", "description", "source_url")
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def dedupe_key(job: dict) -> str:
    """Conservative cross-source identity: same company, title, and stated location."""
    parts = (job.get("company", ""), job.get("title", ""), job.get("location", ""))
    return "|".join(normalized_key(part) for part in parts)


def canonical_job_id(key: str) -> str:
    return f"job:{hashlib.sha256(key.encode()).hexdigest()[:20]}"
