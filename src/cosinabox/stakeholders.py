"""Stakeholder resolver — Attio when enabled, stakeholders.yaml as fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_attio_client: Any = None


def _get_attio_client() -> Any:
    """Lazy-init the Attio client. Returns None if not available."""
    global _attio_client
    if _attio_client is not None:
        return _attio_client
    try:
        from cosinabox.tools.attio import AttioClient

        _attio_client = AttioClient()
        return _attio_client
    except (ImportError, RuntimeError) as exc:
        logger.warning("Attio client unavailable: %s", exc)
        return None


def _load_yaml(config_dir: Path) -> list[dict[str, Any]]:
    """Load stakeholders from YAML fallback."""
    path = config_dir / "stakeholders.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return []
    return data.get("stakeholders", [])


def get_stakeholders(
    *,
    config_dir: Path,
    integrations: dict[str, Any],
    read_only: bool = False,
) -> list[dict[str, Any]]:
    """Get stakeholders from the best available source.

    When Attio is enabled and reachable, returns Attio data.
    Falls back to stakeholders.yaml on failure or when disabled.
    """
    attio_cfg = integrations.get("attio", {})
    if not attio_cfg.get("enabled", False):
        return _load_yaml(config_dir)

    client = _get_attio_client()
    if client is None:
        return _load_yaml(config_dir)

    try:
        return client.list_people(limit=50)
    except Exception:
        logger.warning(
            "Attio API call failed, falling back to stakeholders.yaml",
            exc_info=True,
        )
        return _load_yaml(config_dir)
