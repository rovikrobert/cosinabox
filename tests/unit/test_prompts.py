from __future__ import annotations

from cosinabox.prompts.core import render_system_prompt
from cosinabox.prompts.briefing import render_briefing_prompt


def test_system_prompt_substitutes_personality() -> None:
    out = render_system_prompt(
        personality="You are blunt. Cut filler.",
        name="Alex",
        timezone="America/Los_Angeles",
    )
    assert "Alex" in out
    assert "America/Los_Angeles" in out
    assert "blunt" in out


def test_briefing_prompt_includes_sections() -> None:
    out = render_briefing_prompt(
        personality="Be direct.",
        name="Alex",
        calendar_summary="3 events",
        email_summary="5 emails",
        followups="2 stale",
    )
    assert "Calendar" in out
    assert "Email" in out
    assert "3 events" in out
    assert "5 emails" in out
