from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import yaml

from .db import (
    canonical_job_id,
    content_hash,
    dedupe_key,
    transaction,
    utcnow,
)
from .extraction import (
    benefit_evidence,
    binding_experience_minimum,
    compensation,
    experience_requirements,
    primary_workplace,
    workplace_evidence,
)
from .llm_fallback import ExtractionFallback
from .scoring import score_job


def load_demo_jobs() -> list[dict]:
    path = Path(__file__).parent / "data" / "demo_jobs.json"
    return json.loads(path.read_text())


def load_demo_feeds() -> list[tuple[dict, list[dict]]]:
    partner_path = Path(__file__).parent / "data" / "demo_partner_jobs.json"
    return [
        (
            {
                "id": "demo:primary",
                "kind": "demo",
                "company": "Fictional companies",
                "label": "Sample ATS feed",
            },
            load_demo_jobs(),
        ),
        (
            {
                "id": "demo:partner",
                "kind": "demo",
                "company": "Fictional partner",
                "label": "Sample partner feed",
            },
            json.loads(partner_path.read_text()),
        ),
    ]


def initialize_demo(db, profile: dict | None = None) -> dict[str, int]:
    totals = {"added": 0, "updated": 0, "unchanged": 0, "deduplicated": 0, "deactivated": 0}
    for source, jobs in load_demo_feeds():
        counts = refresh_source(db, source, jobs, profile or load_profile())
        for key, value in counts.items():
            totals[key] += value
    return totals


def load_profile(path: str | Path | None = None) -> dict:
    if path:
        return yaml.safe_load(Path(path).read_text())["profile"]
    return {
        "target_titles": ["product manager", "technical product manager", "product lead"],
        "target_skills": ["ai", "machine learning", "developer tools", "analytics", "platform"],
        "preferred_locations": ["remote", "toronto", "new york", "san francisco"],
        "preferred_workplaces": ["Remote", "Remote or hybrid", "Hybrid"],
        "target_experience_years": 6,
        "minimum_salary": 150_000,
        "minimum_salary_currency": "USD",
    }


def _facts(job: dict, fallback: ExtractionFallback | None = None) -> dict:
    description = job["description"]
    workplaces = workplace_evidence(description, job.get("location", ""))
    experiences = experience_requirements(description)
    pay = compensation(description)
    benefits = benefit_evidence(description)
    experience_min = binding_experience_minimum(description)

    missing = set()
    if not workplaces:
        missing.add("workplace")
    if experience_min is None:
        missing.add("experience_min")
    if pay is None:
        missing.add("compensation")
    if not benefits:
        missing.add("benefits")

    if fallback and missing:
        extra = fallback.extract(description, missing)
        if not workplaces and extra.workplace:
            workplaces = [extra.workplace]
        if experience_min is None and extra.experience_min:
            try:
                experience_min = int(extra.experience_min.value)
                experiences.append(extra.experience_min)
            except ValueError:
                pass
        if pay is None:
            pay = extra.compensation
        if not benefits:
            benefits = list(extra.benefits)

    return {
        "workplace": primary_workplace(workplaces),
        "workplace_evidence": [item.to_dict() for item in workplaces],
        "experience_min": experience_min,
        "experience_evidence": [item.to_dict() for item in experiences],
        "compensation_min": pay.minimum if pay else None,
        "compensation_max": pay.maximum if pay else None,
        "compensation_currency": pay.currency if pay else None,
        "compensation_period": pay.period if pay else None,
        "compensation_evidence": asdict(pay.evidence) if pay else None,
        "benefits": [item.value for item in benefits],
        "benefits_evidence": [item.to_dict() for item in benefits],
    }


def _changed_fields(existing, job: dict) -> list[str]:
    if existing is None:
        return []
    return [
        field
        for field in ("company", "title", "location", "description", "source_url")
        if existing[field] != job.get(field)
    ]


def refresh_source(
    db,
    source: dict,
    jobs: list[dict],
    profile: dict,
    fallback: ExtractionFallback | None = None,
) -> dict[str, int]:
    """Refresh one source atomically; only that source can deactivate its mappings."""
    started = utcnow()
    source_id = source["id"]
    previous = db.execute("SELECT current_jobs FROM sources WHERE id=?", (source_id,)).fetchone()
    if previous and previous["current_jobs"] > 0 and not jobs and not source.get("allow_empty"):
        raise ValueError(
            f"Source {source_id} returned zero roles after previously returning "
            f"{previous['current_jobs']}; refusing to close them without allow_empty"
        )
    counts = {"added": 0, "updated": 0, "unchanged": 0, "deduplicated": 0, "deactivated": 0}
    seen_source_ids: set[str] = set()

    with transaction(db):
        db.execute(
            """INSERT INTO sources(id,kind,company,label,last_status,last_attempt_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,
            company=excluded.company,label=excluded.label,last_attempt_at=excluded.last_attempt_at""",
            (
                source_id,
                source.get("kind", "unknown"),
                source.get("company", source.get("label", source_id)),
                source.get("label", source.get("company", source_id)),
                "running",
                started,
            ),
        )
        run_cursor = db.execute(
            "INSERT INTO runs(source_id,started_at,finished_at,status) VALUES(?,?,?,?)",
            (source_id, started, started, "running"),
        )
        run_id = run_cursor.lastrowid

        for raw in jobs:
            job = dict(raw)
            source_job_id = str(job.get("source_job_id") or job.get("id"))
            if not source_job_id or source_job_id == "None":
                raise ValueError(f"Source {source_id} returned a job without an id")
            seen_source_ids.add(source_job_id)
            key = dedupe_key(job)
            mapping = db.execute(
                "SELECT job_id FROM job_sources WHERE source_id=? AND source_job_id=?",
                (source_id, source_job_id),
            ).fetchone()
            duplicate = False
            if mapping:
                job_id = mapping["job_id"]
            else:
                match = db.execute("SELECT id FROM jobs WHERE dedupe_key=?", (key,)).fetchone()
                duplicate = match is not None
                job_id = match["id"] if match else canonical_job_id(key)
                counts["deduplicated"] += int(duplicate)

            facts = _facts(job, fallback)
            job.update(facts)
            result = score_job(job, profile)
            raw_hash = content_hash(job)
            existing = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            changed_fields = _changed_fields(existing, job)
            now = utcnow()
            first_seen = existing["first_seen"] if existing else now

            should_replace = (
                existing is None
                or source_id == existing["primary_source_id"]
                or (
                    not mapping
                    and (
                        source_id < existing["primary_source_id"]
                        or (
                            source_id == existing["primary_source_id"]
                            and len(job["description"]) > len(existing["description"])
                        )
                    )
                )
            )
            kind = (
                "added"
                if existing is None
                else ("updated" if mapping and should_replace and changed_fields else "unchanged")
            )
            counts[kind] += 1
            if should_replace:
                db.execute(
                    """INSERT INTO jobs(
                    id,dedupe_key,primary_source_id,company,title,location,workplace,workplace_evidence,
                    description,source_url,experience_min,experience_evidence,
                    compensation_min,compensation_max,compensation_currency,compensation_period,
                    compensation_evidence,benefits,benefits_evidence,score,score_breakdown,why,
                    concerns,content_hash,first_seen,last_seen,active)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(id) DO UPDATE SET dedupe_key=excluded.dedupe_key,
                    primary_source_id=excluded.primary_source_id,
                    company=excluded.company,title=excluded.title,location=excluded.location,
                    workplace=excluded.workplace,workplace_evidence=excluded.workplace_evidence,
                    description=excluded.description,source_url=excluded.source_url,
                    experience_min=excluded.experience_min,
                    experience_evidence=excluded.experience_evidence,
                    compensation_min=excluded.compensation_min,
                    compensation_max=excluded.compensation_max,
                    compensation_currency=excluded.compensation_currency,
                    compensation_period=excluded.compensation_period,
                    compensation_evidence=excluded.compensation_evidence,
                    benefits=excluded.benefits,benefits_evidence=excluded.benefits_evidence,
                    score=excluded.score,score_breakdown=excluded.score_breakdown,
                    why=excluded.why,concerns=excluded.concerns,content_hash=excluded.content_hash,
                    last_seen=excluded.last_seen,active=1""",
                    (
                        job_id,
                        key,
                        source_id,
                        job["company"],
                        job["title"],
                        job["location"],
                        job["workplace"],
                        json.dumps(job["workplace_evidence"]),
                        job["description"],
                        job.get("source_url"),
                        job["experience_min"],
                        json.dumps(job["experience_evidence"]),
                        job["compensation_min"],
                        job["compensation_max"],
                        job["compensation_currency"],
                        job["compensation_period"],
                        json.dumps(job["compensation_evidence"]),
                        json.dumps(job["benefits"]),
                        json.dumps(job["benefits_evidence"]),
                        result.total,
                        json.dumps(
                            {
                                name: {"points": points, "maximum": result.maximums[name]}
                                for name, points in result.breakdown.items()
                            }
                        ),
                        json.dumps(result.why),
                        json.dumps(result.concerns),
                        raw_hash,
                        first_seen,
                        now,
                    ),
                )

            prior_mapping = db.execute(
                "SELECT first_seen FROM job_sources WHERE source_id=? AND source_job_id=?",
                (source_id, source_job_id),
            ).fetchone()
            db.execute(
                """INSERT INTO job_sources(
                source_id,source_job_id,job_id,source_url,raw_hash,first_seen,last_seen,active)
                VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(source_id,source_job_id) DO UPDATE SET
                job_id=excluded.job_id,source_url=excluded.source_url,raw_hash=excluded.raw_hash,
                last_seen=excluded.last_seen,active=1""",
                (
                    source_id,
                    source_job_id,
                    job_id,
                    job.get("source_url"),
                    raw_hash,
                    prior_mapping["first_seen"] if prior_mapping else now,
                    now,
                ),
            )
            if kind != "unchanged":
                db.execute(
                    """INSERT INTO changes(
                    run_id,job_id,source_id,kind,detail,changed_fields,observed_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        job_id,
                        source_id,
                        kind,
                        f"{job['company']} — {job['title']}",
                        json.dumps(changed_fields),
                        now,
                    ),
                )

        active_mappings = db.execute(
            "SELECT source_job_id,job_id FROM job_sources WHERE source_id=? AND active=1",
            (source_id,),
        ).fetchall()
        for row in active_mappings:
            if row["source_job_id"] not in seen_source_ids:
                db.execute(
                    "UPDATE job_sources SET active=0 WHERE source_id=? AND source_job_id=?",
                    (source_id, row["source_job_id"]),
                )
                still_active = db.execute(
                    "SELECT 1 FROM job_sources WHERE job_id=? AND active=1 LIMIT 1",
                    (row["job_id"],),
                ).fetchone()
                if not still_active:
                    db.execute("UPDATE jobs SET active=0 WHERE id=?", (row["job_id"],))
                    counts["deactivated"] += 1
                    db.execute(
                        """INSERT INTO changes(
                        run_id,job_id,source_id,kind,detail,changed_fields,observed_at)
                        SELECT ?,id,?,'closed',company || ' — ' || title,'[]',? FROM jobs WHERE id=?""",
                        (run_id, source_id, utcnow(), row["job_id"]),
                    )

        finished = utcnow()
        current_jobs = db.execute(
            "SELECT COUNT(*) FROM job_sources WHERE source_id=? AND active=1", (source_id,)
        ).fetchone()[0]
        db.execute(
            """UPDATE runs SET finished_at=?,status='success',added=?,updated=?,unchanged=?,
            deduplicated=?,deactivated=? WHERE id=?""",
            (
                finished,
                counts["added"],
                counts["updated"],
                counts["unchanged"],
                counts["deduplicated"],
                counts["deactivated"],
                run_id,
            ),
        )
        db.execute(
            """UPDATE sources SET last_status='success',last_error=NULL,last_attempt_at=?,
            last_success_at=?,current_jobs=? WHERE id=?""",
            (finished, finished, current_jobs, source_id),
        )
    return counts


def record_source_failure(db, source: dict, error: Exception) -> None:
    """Record one connector failure without modifying any job or mapping state."""
    now = utcnow()
    message = f"{type(error).__name__}: {error}"[:500]
    with transaction(db):
        db.execute(
            """INSERT INTO sources(id,kind,company,label,last_status,last_error,last_attempt_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,
            company=excluded.company,label=excluded.label,last_status='failed',
            last_error=excluded.last_error,last_attempt_at=excluded.last_attempt_at""",
            (
                source["id"],
                source.get("kind", "unknown"),
                source.get("company", source["id"]),
                source.get("label", source.get("company", source["id"])),
                "failed",
                message,
                now,
            ),
        )
        db.execute(
            """INSERT INTO runs(source_id,started_at,finished_at,status,error)
            VALUES(?,?,?,?,?)""",
            (source["id"], now, now, "failed", message),
        )


def refresh(
    db,
    jobs: list[dict],
    profile: dict,
    source_id: str = "demo:fictional",
    fallback: ExtractionFallback | None = None,
) -> dict[str, int]:
    """Compatibility wrapper for the fictional demo source and small integrations."""
    return refresh_source(
        db,
        {"id": source_id, "kind": "demo", "company": "Fictional demo", "label": "Demo data"},
        jobs,
        profile,
        fallback,
    )
