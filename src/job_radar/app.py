from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import connect, transaction, utcnow
from .ingest import initialize_demo

ROOT = Path(__file__).parent


def _optional_int(value: str, label: str, minimum: int = 0, maximum: int | None = None):
    if not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"{label} must be a whole number") from error
    if parsed < minimum or (maximum is not None and parsed > maximum):
        constraint = (
            f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        )
        raise HTTPException(status_code=422, detail=f"{label} must be {constraint}")
    return parsed


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
                for key in (
                    "benefits",
                    "benefits_evidence",
                    "workplace_evidence",
                    "score_breakdown",
                    "why",
                    "concerns",
                    "tags",
                    "changed_fields",
                ):
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
        location_q: str = "",
        min_score: str = "",
        max_experience: str = "",
        min_compensation: str = "",
        currency: str = "",
        sort: str = "score",
    ):
        min_score_value = _optional_int(min_score, "Minimum score", maximum=100)
        max_experience_value = _optional_int(max_experience, "Maximum experience", maximum=20)
        min_compensation_value = _optional_int(min_compensation, "Minimum compensation")
        clauses = ["j.active=1"]
        params: list[object] = []
        if q:
            clauses.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)")
            params.extend([f"%{q}%"] * 3)
        if status:
            clauses.append("COALESCE(h.status, 'Inbox') = ?")
            params.append(status)
        if workplace:
            clauses.append("j.workplace LIKE ?")
            params.append(f"%{workplace}%")
        if location_q:
            clauses.append("j.location LIKE ?")
            params.append(f"%{location_q}%")
        if min_score_value is not None:
            clauses.append("j.score >= ?")
            params.append(min_score_value)
        if max_experience_value is not None:
            clauses.append("(j.experience_min IS NULL OR j.experience_min <= ?)")
            params.append(max_experience_value)
        if min_compensation_value is not None:
            clauses.append("j.compensation_max >= ?")
            params.append(min_compensation_value)
        if currency:
            clauses.append("j.compensation_currency = ?")
            params.append(currency)
        order_by = {
            "score": "j.score DESC, j.company, j.title",
            "compensation": "j.compensation_max IS NULL, j.compensation_max DESC, j.score DESC",
            "company": "j.company, j.score DESC",
            "newest": "j.first_seen DESC, j.score DESC",
        }.get(sort, "j.score DESC, j.company, j.title")
        jobs = rows(
            """SELECT j.*, COALESCE(h.status,'Inbox') status, COALESCE(h.notes,'') notes,
            COALESCE(h.tags,'[]') tags FROM jobs j LEFT JOIN human_state h ON h.job_id=j.id
            WHERE """
            + " AND ".join(clauses)
            + f" ORDER BY {order_by}",
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
                    "location_q": location_q,
                    "min_score": min_score_value,
                    "max_experience": max_experience_value,
                    "min_compensation": min_compensation_value,
                    "currency": currency,
                    "sort": sort,
                },
                "source_summary": rows(
                    """SELECT COUNT(*) total,
                    SUM(CASE WHEN last_status='failed' THEN 1 ELSE 0 END) failed,
                    MAX(last_success_at) last_success FROM sources"""
                )[0],
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
            raise HTTPException(status_code=404, detail="Job not found")
        items[0]["experience_evidence"] = json.loads(items[0]["experience_evidence"] or "[]")
        items[0]["compensation_evidence"] = json.loads(items[0]["compensation_evidence"] or "null")
        items[0]["sources"] = rows(
            """SELECT s.label,s.kind,js.source_url,js.last_seen FROM job_sources js
            JOIN sources s ON s.id=js.source_id WHERE js.job_id=? ORDER BY s.label""",
            (job_id,),
        )
        return templates.TemplateResponse(request, "detail.html", {"job": items[0]})

    @app.post("/jobs/{job_id}/triage")
    def triage(
        job_id: str, status: str = Form("Inbox"), notes: str = Form(""), tags: str = Form("")
    ):
        allowed_statuses = {"Inbox", "Shortlist", "Applied", "Dismissed"}
        if status not in allowed_statuses:
            raise HTTPException(status_code=422, detail="Invalid status")
        exists = rows("SELECT id FROM jobs WHERE id=?", (job_id,))
        if not exists:
            raise HTTPException(status_code=404, detail="Job not found")
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
            """SELECT j.company, COUNT(*) jobs, ROUND(AVG(j.score),1) average_score,
            MAX(j.score) top_score, MAX(j.last_seen) last_seen,
            SUM(CASE WHEN h.status='Shortlist' THEN 1 ELSE 0 END) shortlisted,
            SUM(CASE WHEN h.status='Applied' THEN 1 ELSE 0 END) applied,
            SUM(CASE WHEN j.workplace LIKE '%Remote%' THEN 1 ELSE 0 END) remote_jobs
            FROM jobs j LEFT JOIN human_state h ON h.job_id=j.id WHERE j.active=1
            GROUP BY j.company ORDER BY top_score DESC, jobs DESC"""
        )
        return templates.TemplateResponse(request, "companies.html", {"companies": companies})

    @app.get("/changes")
    def changes(request: Request):
        return templates.TemplateResponse(
            request,
            "changes.html",
            {
                "changes": rows(
                    "SELECT * FROM changes ORDER BY observed_at DESC, id DESC LIMIT 100"
                ),
                "runs": rows(
                    """SELECT r.*,s.label FROM runs r LEFT JOIN sources s ON s.id=r.source_id
                    ORDER BY r.finished_at DESC,r.id DESC LIMIT 20"""
                ),
            },
        )

    @app.get("/sources")
    def sources(request: Request):
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "sources": rows(
                    """SELECT * FROM sources ORDER BY
                    CASE last_status WHEN 'failed' THEN 0 WHEN 'never_run' THEN 1 ELSE 2 END,label"""
                )
            },
        )

    @app.get("/health")
    def health():
        db = connect(app.state.db_path)
        try:
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
            last_run = db.execute(
                "SELECT finished_at,status FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            failed_sources = db.execute(
                "SELECT COUNT(*) FROM sources WHERE last_status='failed'"
            ).fetchone()[0]
            return {
                "status": "degraded" if failed_sources else "ok",
                "jobs": count,
                "last_refresh": last_run[0] if last_run else None,
                "failed_sources": failed_sources,
            }
        finally:
            db.close()

    @app.post("/demo/reset")
    def reset_demo():
        db = connect(app.state.db_path)
        try:
            initialize_demo(db)
        finally:
            db.close()
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
