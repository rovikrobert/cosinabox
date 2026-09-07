from __future__ import annotations

import pytest
from jsonschema import ValidationError, validate

from cosinabox.schemas import SCHEMA_NAMES, load_schema

MINIMAL = {
    "schema_version": 1,
    "groups": [
        {
            "name": "example-group",
            "priority": 0,
            "search": {"country": "us", "topic": "news", "time_range": "week"},
            "entities": [
                {"name": "Example Org", "aliases": ["ExOrg"], "queries": ["Example Org launch"]}
            ],
        }
    ],
}


def test_research_is_a_registered_schema():
    assert "research" in SCHEMA_NAMES
    assert load_schema("research")["title"] == "research.yaml"


def test_minimal_config_validates():
    validate(instance=MINIMAL, schema=load_schema("research"))


def test_feeds_and_field_queries_are_optional():
    cfg = {**MINIMAL, "feeds": ["https://example.com/rss"], "field_queries": ["video model"]}
    validate(instance=cfg, schema=load_schema("research"))


def test_group_requires_a_priority():
    bad = {"schema_version": 1, "groups": [{"name": "g", "entities": []}]}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=load_schema("research"))


def test_wrong_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        validate(instance={**MINIMAL, "schema_version": 2}, schema=load_schema("research"))


def test_topic_is_constrained_to_tavily_values():
    bad = {
        "schema_version": 1,
        "groups": [{"name": "g", "priority": 0, "search": {"topic": "sideways"}, "entities": []}],
    }
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=load_schema("research"))
