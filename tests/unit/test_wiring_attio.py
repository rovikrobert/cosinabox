"""Wiring tests: describe command with/without Attio."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_describe_with_attio_enabled(tmp_path: Path) -> None:
    """describe uses Attio people when attio integration is enabled."""
    import shutil

    # Copy sample repo to tmp
    shutil.copytree(str(SAMPLE), str(tmp_path / "repo"))
    repo = tmp_path / "repo"

    # Enable attio in integrations.yaml
    integ_path = repo / "integrations.yaml"
    data = yaml.safe_load(integ_path.read_text()) or {}
    data.setdefault("integrations", {})["attio"] = {"enabled": True}
    integ_path.write_text(yaml.dump(data))

    mock_client = MagicMock()
    mock_client.list_people.return_value = [
        {
            "id": "r1",
            "name": "Attio Person",
            "role": "Investor",
            "cadence": None,
            "last_contact": None,
        }
    ]

    import cosinabox.stakeholders as resolver

    runner = CliRunner()
    with patch.object(resolver, "_get_attio_client", return_value=mock_client):
        result = runner.invoke(cli, ["-C", str(repo), "describe"])

    assert result.exit_code == 0
    assert "Attio Person" in result.output


def test_describe_without_attio_uses_yaml(tmp_path: Path) -> None:
    """describe falls back to stakeholders.yaml when attio is disabled."""
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Sarah Chen" in result.output
