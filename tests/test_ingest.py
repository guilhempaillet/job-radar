import json

from job_radar.db import connect
from job_radar.extraction import Compensation, Evidence
from job_radar.ingest import (
    initialize_demo,
    load_demo_jobs,
    load_profile,
    record_source_failure,
    refresh,
)
from job_radar.llm_fallback import FallbackResult


def test_refresh_is_idempotent_and_preserves_human_state(tmp_path):
    db = connect(tmp_path / "radar.db")
    jobs = load_demo_jobs()
    first = refresh(db, jobs, load_profile())
    assert first["added"] == len(jobs)
    job_id = db.execute("SELECT id FROM jobs ORDER BY id LIMIT 1").fetchone()[0]
    db.execute(
        "INSERT INTO human_state(job_id,status,notes,tags,updated_at) VALUES(?,?,?,?,?)",
        (job_id, "Applied", "Kept by refresh", json.dumps(["referral"]), "now"),
    )
    db.commit()
    second = refresh(db, jobs, load_profile())
    assert second == {
        "added": 0,
        "updated": 0,
        "unchanged": len(jobs),
        "deduplicated": 0,
        "deactivated": 0,
    }
    state = db.execute("SELECT status, notes FROM human_state WHERE job_id=?", (job_id,)).fetchone()
    assert tuple(state) == ("Applied", "Kept by refresh")


def test_demo_proves_cross_source_deduplication(tmp_path):
    db = connect(tmp_path / "radar.db")
    counts = initialize_demo(db)
    source_records = db.execute("SELECT COUNT(*) FROM job_sources").fetchone()[0]
    canonical_jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert counts["deduplicated"] == 1
    assert source_records == 10
    assert canonical_jobs == 9
    second = initialize_demo(db)
    assert second == {
        "added": 0,
        "updated": 0,
        "unchanged": 10,
        "deduplicated": 0,
        "deactivated": 0,
    }


def test_change_and_closure_are_auditable_and_source_scoped(tmp_path):
    db = connect(tmp_path / "radar.db")
    jobs = load_demo_jobs()
    refresh(db, jobs, load_profile(), source_id="source:a")
    refresh(db, [dict(jobs[0], source_job_id="other")], load_profile(), source_id="source:b")
    changed = [dict(item) for item in jobs]
    changed[0]["title"] += " II"
    counts = refresh(db, changed[:-1], load_profile(), source_id="source:a")
    assert counts["updated"] == 1
    assert counts["deactivated"] == 1
    assert db.execute("SELECT COUNT(*) FROM changes WHERE kind='closed'").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT COUNT(*) FROM job_sources WHERE source_id='source:b' AND active=1"
        ).fetchone()[0]
        == 1
    )


def test_failed_source_keeps_existing_roles_active(tmp_path):
    db = connect(tmp_path / "radar.db")
    jobs = load_demo_jobs()
    refresh(db, jobs, load_profile(), source_id="source:stable")
    record_source_failure(
        db,
        {"id": "source:stable", "kind": "greenhouse", "company": "Acme", "label": "Acme"},
        RuntimeError("timeout"),
    )
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0] == len(jobs)
    status = db.execute("SELECT last_status FROM sources WHERE id='source:stable'").fetchone()[0]
    assert status == "failed"


def test_suspicious_empty_refresh_fails_closed(tmp_path):
    db = connect(tmp_path / "radar.db")
    refresh(db, load_demo_jobs(), load_profile(), source_id="source:stable")
    try:
        refresh(db, [], load_profile(), source_id="source:stable")
    except ValueError as error:
        assert "refusing to close" in str(error)
    else:
        raise AssertionError("Expected a suspicious empty refresh to fail")
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0] == len(
        load_demo_jobs()
    )


def test_compensation_and_provenance_are_persisted(tmp_path):
    db = connect(tmp_path / "radar.db")
    refresh(db, load_demo_jobs(), load_profile())
    row = db.execute(
        "SELECT compensation_min,compensation_currency,compensation_evidence FROM jobs "
        "WHERE company='Northstar AI' AND title LIKE 'Senior%'"
    ).fetchone()
    evidence = json.loads(row["compensation_evidence"])
    assert row["compensation_min"] == 175_000
    assert row["compensation_currency"] == "USD"
    assert evidence["method"] == "rule"


def test_optional_fallback_only_fills_missing_fields(tmp_path):
    class FakeFallback:
        def extract(self, text, missing_fields):
            assert missing_fields == {"workplace", "experience_min", "compensation", "benefits"}
            return FallbackResult(
                experience_min=Evidence("4", "Four years required", method="llm_fallback"),
                workplace=Evidence("Hybrid", "Two office days", method="llm_fallback"),
                compensation=Compensation(
                    160_000,
                    190_000,
                    "USD",
                    "year",
                    Evidence("$160,000-$190,000", "Salary note", method="llm_fallback"),
                ),
                benefits=(Evidence("Commuter", "Commuter program", method="llm_fallback"),),
            )

    db = connect(tmp_path / "radar.db")
    job = {
        "id": "ambiguous",
        "company": "Example",
        "title": "Product Manager",
        "location": "Flexible",
        "description": "The details are available in a separate structured field.",
        "source_url": "https://example.com/ambiguous",
    }
    refresh(db, [job], load_profile(), fallback=FakeFallback())
    row = db.execute(
        "SELECT experience_min,workplace,compensation_min,benefits_evidence FROM jobs"
    ).fetchone()
    assert tuple(row[:3]) == (4, "Hybrid", 160_000)
    assert json.loads(row["benefits_evidence"])[0]["method"] == "llm_fallback"
