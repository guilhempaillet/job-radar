from fastapi.testclient import TestClient

from job_radar.app import create_app
from job_radar.db import connect
from job_radar.ingest import load_demo_jobs, load_profile, refresh


def client(tmp_path):
    path = tmp_path / "radar.db"
    db = connect(path)
    refresh(db, load_demo_jobs(), load_profile())
    db.close()
    return TestClient(create_app(path))


def test_dashboard_and_views_render(tmp_path):
    web = client(tmp_path)
    assert "Turn a noisy job market" in web.get("/").text
    assert "Company radar" in web.get("/companies").text
    assert "What changed?" in web.get("/changes").text
    assert web.get("/health").json()["jobs"] == len(load_demo_jobs())


def test_filters_and_human_triage(tmp_path):
    web = client(tmp_path)
    assert "Northstar AI" in web.get("/?q=Northstar&workplace=Remote").text
    response = web.post(
        "/jobs/northstar-pm-agents/triage",
        data={"status": "Shortlist", "notes": "Strong fit", "tags": "remote, ai"},
        follow_redirects=True,
    )
    assert "Strong fit" in response.text
    assert "Shortlist" in web.get("/?status=Shortlist").text
