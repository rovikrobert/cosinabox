from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def _write_valid_repo(tmp: Path) -> None:
    (tmp / "personality.md").write_text(
        "---\nschema_version: 1\nname: Alex\ntimezone: America/Los_Angeles\n---\n\n# Voice\nbe direct.\n"
    )
    (tmp / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: X\n    cadence: weekly\n"
    )
    (tmp / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: true\n    schedule: "0 8 * * *"\n'
    )
    (tmp / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  google:\n    enabled: false\n"
    )


def test_validate_passes_for_clean_repo(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "validate"])
    assert result.exit_code == 0
    assert "personality.md PASS" in result.output
    assert "stakeholders.yaml PASS" in result.output


def test_validate_fails_on_bad_cadence(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: X\n    cadence: yearly\n"
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "validate"])
    assert result.exit_code != 0
    assert "stakeholders.yaml FAIL" in result.output
