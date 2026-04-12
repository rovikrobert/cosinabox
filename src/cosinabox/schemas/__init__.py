"""JSON Schemas for user config files."""

from __future__ import annotations

import json
from importlib.resources import files

SCHEMA_NAMES = ("personality", "stakeholders", "jobs", "integrations")


def load_schema(name: str) -> dict:
    raw = files("cosinabox.schemas").joinpath(f"{name}.schema.json").read_text()
    return json.loads(raw)
