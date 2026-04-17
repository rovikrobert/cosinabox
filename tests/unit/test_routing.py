from __future__ import annotations

from cosinabox.agent.routing import Router


def test_default_model_is_sonnet() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("what time is my next meeting?")
    assert model == "claude-sonnet-4-6"
    assert thinking is None
    assert use_advisor is False


def test_strategic_keyword_routes_to_advisor() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("Help me think through our hiring strategy")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is True

    model, thinking, use_advisor = router.choose_model("Draft a board prep document")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is True


def test_dm_mode_allows_full_tool_set() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("dm") == {"gmail", "calendar", "web_search"}


def test_group_mode_restricted_to_safe_subset() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("group") == {"calendar", "web_search"}


def test_short_followup_in_strategic_conversation_stays_strategic() -> None:
    """A short follow-up like 'yes', 'ok', or 'continue' should stay on the
    strategic model when the recent conversation has ANY strategic signal,
    even if the 3-of-4 escalation threshold isn't met."""
    router = Router()
    # Only 2 of 4 recent messages are strategic — below the 3-of-4 escalation
    # threshold, but the current message is a short follow-up that should
    # inherit the conversation's strategic context.
    history = [
        {"role": "user", "content": "What's the weather today?"},
        {"role": "assistant", "content": "It's sunny and 28C."},
        {"role": "user", "content": "Let's discuss our positioning strategy"},
        {"role": "assistant", "content": "Here are the key trade-offs to consider..."},
    ]
    model, thinking, use_advisor = router.choose_model("yes, continue", history)
    assert use_advisor is True, (
        "Short follow-up in a conversation with strategic context should use advisor"
    )


def test_short_message_without_strategic_context_stays_default() -> None:
    """A short message without strategic context should stay on default Sonnet."""
    router = Router()
    casual_history = [
        {"role": "user", "content": "What time is my next meeting?"},
        {"role": "assistant", "content": "Your next meeting is at 3pm."},
    ]
    model, thinking, use_advisor = router.choose_model("ok thanks", casual_history)
    assert use_advisor is False
    assert model == "claude-sonnet-4-6"
