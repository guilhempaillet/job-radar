from pathlib import Path

from job_radar.export import write_sample_artifacts


def test_committed_sample_output_is_deterministic(tmp_path):
    csv_path, markdown_path = write_sample_artifacts(tmp_path)
    committed = Path(__file__).parents[1] / "docs" / "sample-output"
    assert csv_path.read_text() == (committed / csv_path.name).read_text()
    assert markdown_path.read_text() == (committed / markdown_path.name).read_text()
    assert "application status" in markdown_path.read_text()
    assert "description" not in csv_path.read_text().splitlines()[0]
