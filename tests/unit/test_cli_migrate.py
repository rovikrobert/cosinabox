from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "personality.md").write_text(
        "---\nschema_version: 2\nname: A\ntimezone: UTC\n---\n\n# Voice\nbe brief\n"
    )
    (tmp / "stakeholders.yaml").write_text("schema_version: 1\nstakeholders: []\n")
    (tmp / "jobs.yaml").write_text("schema_version: 1\njobs: {}\n")
    (tmp / "integrations.yaml").write_text("schema_version: 1\nintegrations: {}\n")


def test_migrate_noops_at_current_version(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code == 0
    assert "current" in result.output.lower() or "no migrations" in result.output.lower()


def test_migrate_detects_outdated_schema(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "stakeholders.yaml").write_text("schema_version: 0\nstakeholders: []\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert "stakeholders.yaml" in result.output
