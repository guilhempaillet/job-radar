from typer.testing import CliRunner

from job_radar.cli import app

runner = CliRunner()


def test_demo_cli_journey(tmp_path):
    database = tmp_path / "demo.db"
    initialized = runner.invoke(app, ["init-demo", "--db", str(database)])
    assert initialized.exit_code == 0
    assert "9 added" in initialized.stdout
    assert "1 duplicate" in initialized.stdout

    refreshed = runner.invoke(app, ["refresh-demo", "--db", str(database)])
    assert refreshed.exit_code == 0
    assert "'updated': 0" in refreshed.stdout

    health = runner.invoke(app, ["source-health", "--db", str(database)])
    assert health.exit_code == 0
    assert "SUCCESS Sample ATS feed" in health.stdout


def test_source_health_is_clear_before_first_run(tmp_path):
    result = runner.invoke(app, ["source-health", "--db", str(tmp_path / "empty.db")])
    assert result.exit_code == 0
    assert "No sources have run yet" in result.stdout
