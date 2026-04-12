from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_describe_uses_attio_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text(
        "---\nschema_version: 1\nname: Test\ntimezone: UTC\n---\n\n# Voice\nbe direct\n"
    )
    (tmp_path / "jobs.yaml").write_text("schema_version: 1\njobs: {}\n")
    (tmp_path / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  attio:\n    enabled: true\n"
    )
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: YAML Person\n    cadence: weekly\n"
    )
    fake_client = MagicMock()
    fake_client.list_people.return_value = [
        {"id": "1", "name": "Attio Person", "role": "CEO at Co"}
    ]
    with patch(
        "cosinabox.stakeholders._get_attio_client",
        return_value=fake_client,
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["-C", str(tmp_path), "describe"])
    assert "Attio Person" in result.output
    assert "YAML Person" not in result.output


def test_describe_falls_back_to_yaml(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text(
        "---\nschema_version: 1\nname: Test\ntimezone: UTC\n---\n\n# Voice\nbe direct\n"
    )
    (tmp_path / "jobs.yaml").write_text("schema_version: 1\njobs: {}\n")
    (tmp_path / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  attio:\n    enabled: false\n"
    )
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: YAML Person\n    cadence: weekly\n"
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "describe"])
    assert "YAML Person" in result.output
