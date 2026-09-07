import sqlite3

from job_radar.db import connect, dedupe_key


def test_conservative_dedupe_key_normalizes_formatting():
    first = {"company": "Northstar AI", "title": "Product Manager — AI", "location": "Remote, US"}
    second = {"company": "northstar.ai", "title": "Product Manager - AI", "location": "Remote US"}
    assert dedupe_key(first) == dedupe_key(second)


def test_early_demo_database_is_migrated_in_place(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, workplace TEXT,
          description TEXT, source_url TEXT, experience_min INTEGER, experience_evidence TEXT,
          benefits TEXT, score INTEGER, score_breakdown TEXT, why TEXT, concerns TEXT,
          content_hash TEXT, first_seen TEXT, last_seen TEXT, active INTEGER
        );
        CREATE TABLE runs (
          id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,
          added INTEGER, updated INTEGER, unchanged INTEGER
        );
        CREATE TABLE changes (
          id INTEGER PRIMARY KEY, job_id TEXT, kind TEXT, detail TEXT, observed_at TEXT
        );
        """
    )
    db.close()
    migrated = connect(path)
    job_columns = {row[1] for row in migrated.execute("PRAGMA table_info(jobs)")}
    run_columns = {row[1] for row in migrated.execute("PRAGMA table_info(runs)")}
    assert {"primary_source_id", "compensation_min", "benefits_evidence"} <= job_columns
    assert {"source_id", "status", "deactivated"} <= run_columns
