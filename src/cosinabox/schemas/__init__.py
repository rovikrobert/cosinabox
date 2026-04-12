"""JSON Schemas for user config files."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SCHEMA_NAMES = ("personality", "stakeholders", "jobs", "integrations")


def load_schema(name: str) -> dict[str, Any]:
    raw = files("cosinabox.schemas").joinpath(f"{name}.schema.json").read_text()
    result: dict[str, Any] = json.loads(raw)
    return result
