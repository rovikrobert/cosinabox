from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_init_creates_user_repo(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "personality.md").exists()
    assert (target / "stakeholders.yaml").exists()
    assert (target / "jobs.yaml").exists()
    assert (target / "integrations.yaml").exists()
    assert (target / "main.py").exists()
    assert (target / "CLAUDE.md").exists()
    assert (target / "docs" / "agent" / "safety.md").exists()
    assert (target / ".cosinabox" / "pre-commit").exists()
    assert "Open this directory in Claude Code" in result.output


def test_init_refuses_non_empty_dir(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    target.mkdir()
    (target / "junk.txt").write_text("hi")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code != 0
    assert "not empty" in result.output.lower()
