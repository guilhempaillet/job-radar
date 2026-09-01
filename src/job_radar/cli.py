from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn
import yaml

from .app import create_app
from .connectors import fetch_sources
from .db import connect
from .ingest import load_demo_jobs, load_profile, refresh

app = typer.Typer(help="Run and refresh the Job Radar workspace.")
DEFAULT_DB = Path(os.getenv("JOB_RADAR_DB", "job-radar.db"))
DEFAULT_HOST = os.getenv("JOB_RADAR_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("JOB_RADAR_PORT", "8876"))


@app.command("init-demo")
def init_demo(db: Path = Path("job-radar.db")):
    """Create a local database with fictional, privacy-safe sample jobs."""
    connection = connect(db)
    try:
        counts = refresh(connection, load_demo_jobs(), load_profile())
    finally:
        connection.close()
    typer.echo(f"Demo ready at {db}: {counts['added']} added, {counts['updated']} updated")


@app.command()
def serve(
    db: Path = DEFAULT_DB,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
):
    """Open the local dashboard."""
    uvicorn.run(create_app(db), host=host, port=port)


@app.command()
def refresh_demo(db: Path = DEFAULT_DB):
    """Exercise an idempotent refresh using the bundled demo source."""
    connection = connect(db)
    try:
        counts = refresh(connection, load_demo_jobs(), load_profile())
    finally:
        connection.close()
    typer.echo(f"Refresh complete: {counts}")


@app.command()
def refresh_sources(
    config: Path = Path("config.yaml"),
    db: Path = DEFAULT_DB,
):
    """Refresh configured public Greenhouse, Lever, and Ashby boards."""
    settings = yaml.safe_load(config.read_text())
    sources = settings.get("sources", [])
    if not sources:
        raise typer.BadParameter("No sources configured")
    jobs = fetch_sources(sources)
    connection = connect(db)
    try:
        counts = refresh(connection, jobs, load_profile(config))
    finally:
        connection.close()
    typer.echo(f"Fetched {len(jobs)} jobs: {counts}")
