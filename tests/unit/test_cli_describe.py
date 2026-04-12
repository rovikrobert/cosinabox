from __future__ import annotations
from pathlib import Path
from click.testing import CliRunner
from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_describe_outputs_english_summary() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Alex" in result.output
    assert "morning_briefing" in result.output
    assert "Sarah Chen" in result.output


def test_describe_json_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "name" in data
    assert "jobs" in data
