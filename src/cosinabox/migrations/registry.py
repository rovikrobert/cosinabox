"""Migration registry: maps (file, from_version) -> migration callable."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

CURRENT_SCHEMA_VERSION = 1

# Empty for v0.1. Future versions register here:
# REGISTRY[("stakeholders.yaml", 1)] = migrate_stakeholders_1_to_2
REGISTRY: dict[tuple[str, int], Callable[[dict[str, Any]], dict[str, Any]]] = {}
