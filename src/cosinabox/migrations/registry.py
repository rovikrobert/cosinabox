"""Migration registry: maps (file, from_version) -> migration callable."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Engine-wide fallback used by consumers (e.g., the doctor's schema_outdated
# check) that aren't aware of per-file versioning. Bump when the majority of
# files advance. Currently only personality.md is at v2 — keep this at 1 until
# a second file advances.
CURRENT_SCHEMA_VERSION = 1

# Per-file current schema versions. Consumers that know exactly which file
# they're inspecting (e.g., the `migrate` CLI) should prefer this mapping.
# Files not listed default to CURRENT_SCHEMA_VERSION.
CURRENT_VERSIONS: dict[str, int] = {
    "personality.md": 2,
    "stakeholders.yaml": 1,
    "jobs.yaml": 1,
    "integrations.yaml": 1,
}


def _migrate_personality_1_to_2(data: dict[str, Any]) -> dict[str, Any]:
    """Personality v1 -> v2. Adds no new required keys; only bumps the
    version. The new optional ``consult_brainstorm_override`` field is
    picked up by readers that support v2 without needing to be present."""
    out = dict(data)
    out["schema_version"] = 2
    return out


# Maps (filename, from_version) -> migration callable. A missing entry for
# (filename, v) where v < current means the gap is not automatically
# migratable and the CLI should surface a clear error.
REGISTRY: dict[tuple[str, int], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("personality.md", 1): _migrate_personality_1_to_2,
}


def current_version(filename: str) -> int:
    """Return the current schema version for ``filename`` (or the
    engine-wide fallback if the file isn't individually tracked)."""
    return CURRENT_VERSIONS.get(filename, CURRENT_SCHEMA_VERSION)
