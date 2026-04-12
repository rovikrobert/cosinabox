from __future__ import annotations
from pathlib import Path
import yaml
from click.testing import CliRunner
from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: false\n    schedule: "0 8 * * *"\n'
    )


def test_enable_job_flips_flag(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "enable-job", "morning_briefing"])
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["enabled"] is True


def test_disable_job_flips_flag(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: true\n'
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "disable-job", "morning_briefing"])
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["enabled"] is False
