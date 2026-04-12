from __future__ import annotations
from pathlib import Path
from click.testing import CliRunner
from cosinabox.cli.main import cli


def test_set_persona_creates_file(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "set-persona", "--role", "founder"])
    assert result.exit_code == 0
    text = (tmp_path / "personality.md").read_text()
    assert "schema_version: 1" in text
    assert "# Voice" in text


def test_set_persona_refuses_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "set-persona", "--role", "founder"])
    assert result.exit_code != 0


def test_set_persona_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "set-persona", "--role", "founder", "--force"])
    assert result.exit_code == 0
    assert "schema_version: 1" in (tmp_path / "personality.md").read_text()
