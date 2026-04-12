from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: Existing\n    cadence: weekly\n"
    )


def test_add_stakeholder_appends(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "-C",
            str(tmp_path),
            "add-stakeholder",
            "--name",
            "Sarah Chen",
            "--role",
            "Lead investor",
            "--cadence",
            "weekly",
            "--notes",
            "Replies in mornings.",
        ],
    )
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "stakeholders.yaml").read_text())
    names = [s["name"] for s in data["stakeholders"]]
    assert "Sarah Chen" in names


def test_add_stakeholder_rejects_duplicate(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "add-stakeholder", "--name", "Existing", "--cadence", "weekly"]
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_add_stakeholder_rejects_bad_cadence(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "add-stakeholder", "--name", "X", "--cadence", "yearly"]
    )
    assert result.exit_code != 0
