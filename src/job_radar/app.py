from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import connect, transaction, utcnow
from .ingest import load_demo_jobs, load_profile, refresh

ROOT = Path(__file__).parent


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = str(db_path or os.getenv("JOB_RADAR_DB", "job-radar.db"))
    app = FastAPI(title="Job Radar", version="0.1.0")
    app.state.db_path = path
    templates = Jinja2Templates(directory=ROOT / "templates")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    def rows(query: str, params: tuple = ()) -> list[dict]:
        db = connect(app.state.db_path)
        try:
            result = []
            for row in db.execute(query, params).fetchall():
                item = dict(row)
                for key in ("benefits", "score_breakdown", "why", "concerns", "tags"):
                    if key in item and isinstance(item[key], str):
                        item[key] = json.loads(item[key] or "[]")
                result.append(item)
            return result
        finally:
            db.close()

    @app.get("/")
    def index(
        request: Request,
        q: str = "",
        status: str = "",
        workplace: str = "",
        min_score: int = 0,
        max_experience: int | None = None,
    ):
        clauses = ["j.active=1"]
        params: list[object] = []
        if q:
            clauses.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)")
            params.extend([f"%{q}%"] * 3)
        if status:
            clauses.append("COALESCE(h.status, 'Inbox') = ?")
            params.append(status)
        if workplace:
            clauses.append("j.workplace = ?")
            params.append(workplace)
        if min_score:
            clauses.append("j.score >= ?")
            params.append(min_score)
        if max_experience is not None:
            clauses.append("(j.experience_min IS NULL OR j.experience_min <= ?)")
            params.append(max_experience)
        jobs = rows(
            """SELECT j.*, COALESCE(h.status,'Inbox') status, COALESCE(h.notes,'') notes,
            COALESCE(h.tags,'[]') tags FROM jobs j LEFT JOIN human_state h ON h.job_id=j.id
            WHERE """
            + " AND ".join(clauses)
            + " ORDER BY j.score DESC, j.company, j.title",
            tuple(params),
        )
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "jobs": jobs,
                "filters": {
                    "q": q,
                    "status": status,
                    "workplace": workplace,
                    "min_score": min_score,
                    "max_experience": max_experience,
                },
            },
        )

    @app.get("/jobs/{job_id}")
    def detail(request: Request, job_id: str):
        items = rows(
            """SELECT j.*, COALESCE(h.status,'Inbox') status, COALESCE(h.notes,'') notes,
            COALESCE(h.tags,'[]') tags FROM jobs j LEFT JOIN human_state h ON h.job_id=j.id
            WHERE j.id=?""",
            (job_id,),
        )
        if not items:
            return RedirectResponse("/", status_code=303)
        items[0]["experience_evidence"] = json.loads(items[0]["experience_evidence"] or "[]")
        return templates.TemplateResponse(request, "detail.html", {"job": items[0]})

    @app.post("/jobs/{job_id}/triage")
    def triage(
        job_id: str, status: str = Form("Inbox"), notes: str = Form(""), tags: str = Form("")
    ):
        clean_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        db = connect(app.state.db_path)
        try:
            with transaction(db):
                db.execute(
                    """INSERT INTO human_state(job_id,status,notes,tags,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, notes=excluded.notes,
                    tags=excluded.tags, updated_at=excluded.updated_at""",
                    (job_id, status, notes.strip(), json.dumps(clean_tags), utcnow()),
                )
        finally:
            db.close()
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.get("/companies")
    def companies(request: Request):
        companies = rows(
            """SELECT company, COUNT(*) jobs, ROUND(AVG(score),1) average_score,
            MAX(score) top_score, MAX(last_seen) last_seen FROM jobs WHERE active=1
            GROUP BY company ORDER BY top_score DESC, jobs DESC"""
        )
        return templates.TemplateResponse(request, "companies.html", {"companies": companies})

    @app.get("/changes")
    def changes(request: Request):
        return templates.TemplateResponse(
            request,
            "changes.html",
            {"changes": rows("SELECT * FROM changes ORDER BY observed_at DESC, id DESC LIMIT 100")},
        )

    @app.get("/health")
    def health():
        db = connect(app.state.db_path)
        try:
            count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            last_run = db.execute(
                "SELECT finished_at FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return {
                "status": "ok",
                "jobs": count,
                "last_refresh": last_run[0] if last_run else None,
            }
        finally:
            db.close()

    @app.post("/demo/reset")
    def reset_demo():
        db = connect(app.state.db_path)
        try:
            refresh(db, load_demo_jobs(), load_profile())
        finally:
            db.close()
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
