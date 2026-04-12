"""Tests for stakeholder resolver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data))


def test_yaml_fallback_when_attio_disabled(tmp_path: Path) -> None:
    from cosinabox.stakeholders import get_stakeholders

    _write_yaml(
        tmp_path / "stakeholders.yaml",
        {"stakeholders": [{"name": "Alice", "role": "CTO"}]},
    )
    integrations: dict = {"attio": {"enabled": False}}
    result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert len(result) == 1
    assert result[0]["name"] == "Alice"


def test_attio_enabled_returns_attio_data(tmp_path: Path) -> None:
    import cosinabox.stakeholders as resolver
    from cosinabox.stakeholders import get_stakeholders

    mock_client = MagicMock()
    mock_client.list_people.return_value = [{"id": "r1", "name": "Bob", "role": "CEO"}]

    integrations: dict = {"attio": {"enabled": True}}
    with patch.object(resolver, "_get_attio_client", return_value=mock_client):
        result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert result == [{"id": "r1", "name": "Bob", "role": "CEO"}]


def test_attio_error_falls_back_to_yaml(tmp_path: Path) -> None:
    import cosinabox.stakeholders as resolver
    from cosinabox.stakeholders import get_stakeholders

    _write_yaml(
        tmp_path / "stakeholders.yaml",
        {"stakeholders": [{"name": "Carol", "role": "VP"}]},
    )

    mock_client = MagicMock()
    mock_client.list_people.side_effect = Exception("network error")

    integrations: dict = {"attio": {"enabled": True}}
    with patch.object(resolver, "_get_attio_client", return_value=mock_client):
        result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert len(result) == 1
    assert result[0]["name"] == "Carol"


def test_empty_returns_empty_list(tmp_path: Path) -> None:
    from cosinabox.stakeholders import get_stakeholders

    integrations: dict = {"attio": {"enabled": False}}
    result = get_stakeholders(config_dir=tmp_path, integrations=integrations)
    assert result == []
