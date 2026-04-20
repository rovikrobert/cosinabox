# ruff: noqa: I001  # see test_agent_failover.py — pre-commit/CI ruff version skew
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


def test_describe_shows_consult_metrics_when_mcp_installed() -> None:
    """When the ``mcp`` extra is installed, describe adds a 'Consult' section
    showing today's call count, cost, and average latency. Fresh metrics
    singleton => all zeros.
    """
    from cosinabox.consult import reset_default_metrics

    reset_default_metrics()  # start from a clean singleton

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Consult:" in result.output
    assert "0 calls today" in result.output


def test_describe_shows_consult_metrics_with_nonzero_counts(monkeypatch) -> None:
    """Mocked metrics => describe surfaces the actual values (not zeros)."""
    fake_snapshot = {
        "calls_today": 5,
        "cost_today_usd": 0.25,
        "avg_latency_ms": 1200,
        "last_call": "2026-04-20T12:00:00+00:00",
    }
    from unittest.mock import MagicMock

    fake_metrics = MagicMock()
    fake_metrics.snapshot.return_value = fake_snapshot
    monkeypatch.setattr("cosinabox.consult.metrics.get_default_metrics", lambda: fake_metrics)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Consult:" in result.output
    assert "5 calls today" in result.output
    assert "0.25" in result.output or "$0.25" in result.output
    assert "1200" in result.output


def test_describe_skips_consult_section_when_mcp_missing(monkeypatch) -> None:
    """If ``mcp`` isn't installed (``find_spec("mcp")`` returns None), the
    Consult section is omitted entirely — no placeholder, no error.
    """
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "mcp":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("cosinabox.cli.describe.importlib.util.find_spec", fake_find_spec)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Consult:" not in result.output


def test_describe_shows_commitment_counts_when_db_present(tmp_path) -> None:
    """With a memory.db carrying a few commitments, describe should show
    counts. Without the db (fresh repo), the section is silently omitted.
    """
    import shutil

    # Clone the sample fixture so we don't pollute it with a DB.
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)

    from cosinabox.commitments import close_commitment, create_commitment
    from cosinabox.memory import Memory

    db_dir = repo / ".cosinabox"
    db_dir.mkdir(parents=True, exist_ok=True)
    db = Memory(db_path=db_dir / "memory.db")
    a = create_commitment(db, title="open")
    b = create_commitment(db, title="will close")
    close_commitment(db, b["id"])
    db.close()
    _ = a  # silence

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(repo), "describe"])
    assert result.exit_code == 0
    assert "Commitments:" in result.output
    assert "1 open" in result.output
    assert "1 done" in result.output
