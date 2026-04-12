from __future__ import annotations
import json
from pathlib import Path
from click.testing import CliRunner
from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"

def test_doctor_runs_all_checks() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor"])
    for n in ("personality_thin", "stakeholders_empty", "cost_runaway",
        "tool_loop_excess", "prep_noise", "briefing_drift",
        "secret_in_tracked_file", "stale_followups", "oauth_expiring",
        "schema_outdated"):
        assert n in result.output

def test_doctor_json_mode_emits_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--json"])
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) == 10
    assert all("name" in r and "status" in r for r in parsed)
