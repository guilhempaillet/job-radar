from fastapi.testclient import TestClient

from job_radar.app import create_app
from job_radar.db import connect
from job_radar.ingest import initialize_demo


def client(tmp_path):
    path = tmp_path / "radar.db"
    db = connect(path)
    initialize_demo(db)
    db.close()
    return TestClient(create_app(path))


def test_primary_journey_views_render(tmp_path):
    web = client(tmp_path)
    home = web.get("/")
    assert "Turn scattered job boards" in home.text
    assert "COMPENSATION" in home.text
    assert "Company radar" in web.get("/companies").text
    assert "What changed?" in web.get("/changes").text
    assert "Know what ran" in web.get("/sources").text
    health = web.get("/health").json()
    assert health == {
        "status": "ok",
        "jobs": 9,
        "last_refresh": health["last_refresh"],
        "failed_sources": 0,
    }


def test_filters_and_human_triage(tmp_path):
    web = client(tmp_path)
    filtered = web.get("/?q=Northstar&workplace=Remote&location_q=Canada&min_compensation=200000")
    assert "Northstar AI" in filtered.text
    assert "Meridian Labs" not in filtered.text
    db = connect(web.app.state.db_path)
    job_id = db.execute(
        "SELECT id FROM jobs WHERE company='Northstar AI' AND title LIKE 'Senior%'"
    ).fetchone()[0]
    db.close()
    response = web.post(
        f"/jobs/{job_id}/triage",
        data={"status": "Shortlist", "notes": "Strong fit", "tags": "remote, ai"},
        follow_redirects=True,
    )
    assert "Strong fit" in response.text
    assert "Shortlist" in web.get("/?status=Shortlist").text


def test_filter_form_accepts_blank_numeric_fields(tmp_path):
    web = client(tmp_path)
    response = web.get(
        "/?q=northstar&location_q=&status=&workplace=&min_score=&max_experience="
        "&min_compensation=&currency=&sort=score"
    )
    assert response.status_code == 200
    assert "Northstar AI" in response.text
    assert "Lattice Forge" not in response.text
    assert web.get("/?min_score=101").status_code == 422
    assert web.get("/?min_compensation=not-a-number").status_code == 422


def test_invalid_triage_is_rejected(tmp_path):
    web = client(tmp_path)
    db = connect(web.app.state.db_path)
    job_id = db.execute("SELECT id FROM jobs LIMIT 1").fetchone()[0]
    db.close()
    assert web.post(f"/jobs/{job_id}/triage", data={"status": "Hacked"}).status_code == 422
    assert web.get("/jobs/missing").status_code == 404
