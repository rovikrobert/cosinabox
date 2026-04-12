from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from cosinabox.stakeholders import get_stakeholders


def test_returns_yaml_when_attio_disabled(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: Alice\n    cadence: weekly\n"
    )
    integrations: dict[str, Any] = {"attio": {"enabled": False}}
    result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert len(result) == 1
    assert result[0]["name"] == "Alice"


def test_returns_attio_when_enabled(tmp_path: Path) -> None:
    fake_client = MagicMock()
    fake_client.list_people.return_value = [
        {"id": "1", "name": "Sarah Chen", "role": "Investor at Sequoia"}
    ]
    integrations: dict[str, Any] = {"attio": {"enabled": True}}
    with patch(
        "cosinabox.stakeholders._get_attio_client",
        return_value=fake_client,
    ):
        result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert len(result) == 1
    assert result[0]["name"] == "Sarah Chen"


def test_falls_back_to_yaml_on_attio_error(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: Fallback\n    cadence: monthly\n"
    )
    fake_client = MagicMock()
    fake_client.list_people.side_effect = RuntimeError("API down")
    integrations: dict[str, Any] = {"attio": {"enabled": True}}
    with patch(
        "cosinabox.stakeholders._get_attio_client",
        return_value=fake_client,
    ):
        result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert len(result) == 1
    assert result[0]["name"] == "Fallback"


def test_returns_empty_when_no_attio_and_no_yaml(tmp_path: Path) -> None:
    integrations: dict[str, Any] = {"attio": {"enabled": False}}
    result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert result == []
