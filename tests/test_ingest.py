import json

from job_radar.db import connect
from job_radar.ingest import load_demo_jobs, load_profile, refresh


def test_refresh_is_idempotent_and_preserves_human_state(tmp_path):
    db = connect(tmp_path / "radar.db")
    jobs = load_demo_jobs()
    first = refresh(db, jobs, load_profile())
    assert first["added"] == len(jobs)
    db.execute(
        "INSERT INTO human_state(job_id,status,notes,tags,updated_at) VALUES(?,?,?,?,?)",
        (jobs[0]["id"], "Applied", "Kept by refresh", json.dumps(["referral"]), "now"),
    )
    db.commit()
    second = refresh(db, jobs, load_profile())
    assert second == {"added": 0, "updated": 0, "unchanged": len(jobs)}
    state = db.execute(
        "SELECT status, notes FROM human_state WHERE job_id=?", (jobs[0]["id"],)
    ).fetchone()
    assert tuple(state) == ("Applied", "Kept by refresh")


def test_change_is_auditable(tmp_path):
    db = connect(tmp_path / "radar.db")
    jobs = load_demo_jobs()
    refresh(db, jobs, load_profile())
    changed = [dict(x) for x in jobs]
    changed[0]["title"] += " II"
    counts = refresh(db, changed, load_profile())
    assert counts["updated"] == 1
    assert db.execute("SELECT COUNT(*) FROM changes WHERE kind='updated'").fetchone()[0] == 1
