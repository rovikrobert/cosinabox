"""Stakeholder resolver — Attio CRM or YAML fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_attio_client: Any = None


def _get_attio_client() -> Any:
    global _attio_client
    if _attio_client is None:
        from cosinabox.tools.attio import AttioClient

        _attio_client = AttioClient()
    return _attio_client


def get_stakeholders(
    *,
    config_dir: Path,
    integrations: dict[str, Any],
    read_only: bool = False,
) -> list[dict[str, Any]]:
    """Return stakeholders list from Attio (if enabled) or stakeholders.yaml fallback."""
    attio_cfg = integrations.get("attio", {})
    if attio_cfg.get("enabled"):
        try:
            client = _get_attio_client()
            attio_people = client.list_people()
            result: list[dict[str, Any]] = attio_people
            return result
        except Exception:
            logger.warning(
                "Attio CRM enabled but unreachable — falling back to "
                "stakeholders.yaml. CRM search will be unavailable in DM.",
                exc_info=True,
            )

    path = config_dir / "stakeholders.yaml"
    if not path.exists():
        fallback: list[dict[str, Any]] = []
        return fallback
    data = yaml.safe_load(path.read_text()) or {}
    yaml_result: list[dict[str, Any]] = data.get("stakeholders", [])
    return yaml_result
