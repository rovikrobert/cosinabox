from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
USER_REPO = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_simulate_morning_briefing_with_mocked_anthropic(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(USER_REPO), "simulate", "morning_briefing", "--fixture=sample"],
    )
    assert result.exit_code == 0
    assert "morning_briefing" in result.output.lower() or "Briefing" in result.output
