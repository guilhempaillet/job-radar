from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn
import yaml

from .app import create_app
from .connectors import fetch_sources
from .db import connect
from .export import write_sample_artifacts
from .ingest import (
    initialize_demo,
    record_source_failure,
    refresh_source,
)
from .llm_fallback import fallback_from_config

app = typer.Typer(help="Run and refresh the Job Radar workspace.")
DEFAULT_DB = Path(os.getenv("JOB_RADAR_DB", "job-radar.db"))
DEFAULT_HOST = os.getenv("JOB_RADAR_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("JOB_RADAR_PORT", "8876"))


@app.command("init-demo")
def init_demo(db: Path = Path("job-radar.db")):
    """Create a local database with fictional, privacy-safe sample jobs."""
    connection = connect(db)
    try:
        counts = initialize_demo(connection)
    finally:
        connection.close()
    typer.echo(
        f"Demo ready at {db}: {counts['added']} added, "
        f"{counts['deduplicated']} duplicate source record merged"
    )


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
        counts = initialize_demo(connection)
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
    try:
        fallback = fallback_from_config(settings)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    results = fetch_sources(sources)
    connection = connect(db)
    try:
        totals = {
            "fetched": 0,
            "added": 0,
            "updated": 0,
            "unchanged": 0,
            "deduplicated": 0,
            "deactivated": 0,
            "failed_sources": 0,
        }
        for result in results:
            if result.error:
                record_source_failure(connection, result.source, result.error)
                totals["failed_sources"] += 1
                typer.echo(f"FAILED {result.source['label']}: {result.error}", err=True)
                continue
            try:
                counts = refresh_source(
                    connection, result.source, list(result.jobs), settings["profile"], fallback
                )
            except Exception as error:  # noqa: BLE001 - source boundary must remain isolated
                record_source_failure(connection, result.source, error)
                totals["failed_sources"] += 1
                typer.echo(f"FAILED {result.source['label']}: {error}", err=True)
                continue
            totals["fetched"] += len(result.jobs)
            for key, value in counts.items():
                totals[key] += value
            typer.echo(f"OK {result.source['label']}: {len(result.jobs)} roles")
    finally:
        connection.close()
    typer.echo(f"Refresh complete: {totals}")
    if totals["failed_sources"] == len(results):
        raise typer.Exit(code=1)


@app.command()
def source_health(db: Path = DEFAULT_DB):
    """Print the latest status for every configured source."""
    connection = connect(db)
    try:
        rows = connection.execute(
            """SELECT label,kind,last_status,current_jobs,last_attempt_at,last_error
            FROM sources ORDER BY label"""
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        typer.echo("No sources have run yet.")
        return
    for row in rows:
        detail = f" — {row['last_error']}" if row["last_error"] else ""
        typer.echo(
            f"{row['last_status'].upper():7} {row['label']} ({row['kind']}) · "
            f"{row['current_jobs']} active · {row['last_attempt_at']}{detail}"
        )


@app.command()
def export_sample(output_dir: Path = Path("docs/sample-output")):
    """Generate deterministic, privacy-safe CSV and Markdown sample output."""
    csv_path, markdown_path = write_sample_artifacts(output_dir)
    typer.echo(f"Wrote {csv_path} and {markdown_path}")
