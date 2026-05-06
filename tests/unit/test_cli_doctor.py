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
    for n in (
        "personality_thin",
        "stakeholders_empty",
        "cost_runaway",
        "tool_loop_excess",
        "prep_noise",
        "briefing_drift",
        "secret_in_tracked_file",
        "stale_followups",
        "oauth_expiring",
        "schema_outdated",
    ):
        assert n in result.output


def test_doctor_json_mode_emits_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--json"])
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    # 10 existing checks + the new oauth_refresh_live = 11.
    assert len(parsed) == 11
    assert all("name" in r and "status" in r for r in parsed)


def test_doctor_default_includes_live_oauth_check() -> None:
    """Default run (no --offline) must include the new live OAuth check."""
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor"])
    assert "oauth_refresh_live" in result.output


def test_doctor_offline_skips_network_checks() -> None:
    """--offline must filter out checks where network=True so doctor
    can run in CI / on planes without spurious failures.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--offline"])
    assert "oauth_refresh_live" not in result.output
    # Static checks still run.
    assert "personality_thin" in result.output


def test_doctor_offline_json_mode_omits_network_checks() -> None:
    """--offline must work with --json too — the JSON list is shorter."""
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--offline", "--json"])
    parsed = json.loads(result.output)
    names = [r["name"] for r in parsed]
    assert "oauth_refresh_live" not in names
    # Other 10 checks still present.
    assert len(parsed) == 10
