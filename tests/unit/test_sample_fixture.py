from __future__ import annotations

import json
from pathlib import Path

import yaml

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample"


def test_calendar_has_8_events_with_conflict() -> None:
    events = json.loads((FIXTURE / "calendar_events.json").read_text())
    assert len(events) == 8
    summaries = {e["summary"] for e in events}
    assert "Conflict A" in summaries
    assert "Conflict B (overlaps A)" in summaries


def test_emails_has_12() -> None:
    msgs = json.loads((FIXTURE / "emails.json").read_text())
    assert len(msgs) == 12


def test_stakeholders_has_5() -> None:
    data = yaml.safe_load((FIXTURE / "stakeholders.yaml").read_text())
    assert len(data["stakeholders"]) == 5


def test_personality_has_stakes() -> None:
    text = (FIXTURE / "personality.md").read_text()
    assert "Stakes" in text
