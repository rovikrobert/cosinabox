from __future__ import annotations

from cosinabox.prompts.briefing import render_briefing_prompt
from cosinabox.prompts.core import render_system_prompt


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


def test_system_prompt_includes_commitment_capture_rules() -> None:
    """Without an explicit capture instruction the agent will only use
    commitment_create when the user says "remind me". The prompt must
    teach the broader capture surface (intents, closes, dismisses)
    because that's how the commitments subsystem is meant to feel —
    zero-friction capture, not another tool the user has to invoke.
    """
    out = render_system_prompt(
        personality="blunt",
        name="Alex",
        timezone="UTC",
    )
    assert "COMMITMENT CAPTURE" in out
    assert "commitment_create" in out
    assert "commitment_close" in out
    assert "commitment_dismiss" in out
    assert "commitment_list" in out
    # Must distinguish query-vs-commitment so "what's on today?" doesn't
    # create a commitment.
    assert "queries, not commitments" in out
    # Must prefer capture over omission per the spec.
    assert "prefer capture over omission" in out


def test_system_prompt_includes_tool_warnings_rule():
    from cosinabox.prompts.core import render_system_prompt

    rendered = render_system_prompt(personality="(test)", name="Sam", timezone="UTC")
    assert "WARNING:" in rendered
    # Instruction must cover surfacing
    assert "surface" in rendered.lower() or "show" in rendered.lower()
