from __future__ import annotations

import json
from pathlib import Path

import yaml

from .db import content_hash, transaction, utcnow
from .extraction import (
    benefits,
    binding_experience_minimum,
    experience_requirements,
    workplace_evidence,
)
from .scoring import score_job


def load_demo_jobs() -> list[dict]:
    path = Path(__file__).parent / "data" / "demo_jobs.json"
    return json.loads(path.read_text())


def load_profile(path: str | Path | None = None) -> dict:
    if path:
        return yaml.safe_load(Path(path).read_text())["profile"]
    return {
        "target_titles": ["product manager", "technical product manager", "product lead"],
        "target_skills": ["ai", "machine learning", "developer tools", "analytics", "platform"],
        "preferred_locations": ["remote", "toronto", "new york", "san francisco"],
        "target_experience_years": 6,
    }


def refresh(db, jobs: list[dict], profile: dict) -> dict[str, int]:
    started = utcnow()
    counts = {"added": 0, "updated": 0, "unchanged": 0}
    seen: set[str] = set()
    with transaction(db):
        for raw in jobs:
            job = dict(raw)
            seen.add(job["id"])
            workplace = workplace_evidence(job["description"], job.get("location", ""))
            exp_items = experience_requirements(job["description"])
            job["workplace"] = workplace.value if workplace else None
            job["experience_min"] = binding_experience_minimum(job["description"])
            job["experience_evidence"] = json.dumps([item.__dict__ for item in exp_items])
            job["benefits"] = benefits(job["description"])
            result = score_job(job, profile)
            job_hash = content_hash(job)
            existing = db.execute(
                "SELECT content_hash FROM jobs WHERE id = ?", (job["id"],)
            ).fetchone()
            kind = (
                "added"
                if existing is None
                else ("updated" if existing[0] != job_hash else "unchanged")
            )
            counts[kind] += 1
            now = utcnow()
            first_seen = (
                now
                if existing is None
                else db.execute(
                    "SELECT first_seen FROM jobs WHERE id = ?", (job["id"],)
                ).fetchone()[0]
            )
            db.execute(
                """INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET company=excluded.company, title=excluded.title,
                location=excluded.location, workplace=excluded.workplace,
                description=excluded.description, source_url=excluded.source_url,
                experience_min=excluded.experience_min,
                experience_evidence=excluded.experience_evidence, benefits=excluded.benefits,
                score=excluded.score, score_breakdown=excluded.score_breakdown,
                why=excluded.why, concerns=excluded.concerns, content_hash=excluded.content_hash,
                last_seen=excluded.last_seen, active=1""",
                (
                    job["id"],
                    job["company"],
                    job["title"],
                    job["location"],
                    job["workplace"],
                    job["description"],
                    job.get("source_url"),
                    job["experience_min"],
                    job["experience_evidence"],
                    json.dumps(job["benefits"]),
                    result.total,
                    json.dumps(result.breakdown),
                    json.dumps(result.why),
                    json.dumps(result.concerns),
                    job_hash,
                    first_seen,
                    now,
                ),
            )
            if kind != "unchanged":
                db.execute(
                    "INSERT INTO changes(job_id, kind, detail, observed_at) VALUES(?,?,?,?)",
                    (job["id"], kind, f"{job['company']} — {job['title']}", now),
                )
        if seen:
            placeholders = ",".join("?" for _ in seen)
            db.execute(f"UPDATE jobs SET active=0 WHERE id NOT IN ({placeholders})", tuple(seen))
        db.execute(
            "INSERT INTO runs(started_at, finished_at, added, updated, unchanged) VALUES(?,?,?,?,?)",
            (started, utcnow(), counts["added"], counts["updated"], counts["unchanged"]),
        )
    return counts
