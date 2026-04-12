from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "jobs.yaml").write_text(
        "schema_version: 1\njobs:\n  morning_briefing:\n"
        '    enabled: true\n    schedule: "0 8 * * *"\n'
    )


def test_set_schedule_updates_field(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule", "morning_briefing", "--cron", "0 7 * * *"]
    )
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["schedule"] == "0 7 * * *"


def test_set_schedule_rejects_unknown_job(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule", "no_such", "--cron", "0 7 * * *"]
    )
    assert result.exit_code != 0


def test_set_schedule_rejects_bad_cron(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule", "morning_briefing", "--cron", "not a cron"]
    )
    assert result.exit_code != 0
