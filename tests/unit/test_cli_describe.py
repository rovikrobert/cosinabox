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
