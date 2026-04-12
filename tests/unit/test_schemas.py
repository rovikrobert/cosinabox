from __future__ import annotations

import pytest
from jsonschema import ValidationError, validate

from cosinabox.schemas import SCHEMA_NAMES, load_schema


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_loads(name: str) -> None:
    schema = load_schema(name)
    assert schema["$schema"].startswith("https://json-schema.org")


def test_stakeholders_valid() -> None:
    schema = load_schema("stakeholders")
    validate(
        instance={
            "schema_version": 1,
            "stakeholders": [{"name": "X", "cadence": "weekly", "last_contact": "2026-01-01"}],
        },
        schema=schema,
    )


def test_stakeholders_invalid_cadence() -> None:
    schema = load_schema("stakeholders")
    with pytest.raises(ValidationError):
        validate(
            instance={
                "schema_version": 1,
                "stakeholders": [{"name": "X", "cadence": "yearly"}],
            },
            schema=schema,
        )


def test_jobs_valid() -> None:
    schema = load_schema("jobs")
    validate(
        instance={
            "schema_version": 1,
            "jobs": {"morning_briefing": {"enabled": True, "schedule": "0 8 * * *"}},
        },
        schema=schema,
    )
