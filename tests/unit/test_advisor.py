from __future__ import annotations

import cosinabox.defaults as defaults
from cosinabox.agent.cost import estimate_cost, estimate_cost_with_advisor
from cosinabox.agent.loop import _strip_advisor_blocks
from cosinabox.agent.routing import Router


def test_opus_signal_routes_to_advisor() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("What's our strategy for Q3?")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is True
    assert thinking is None


def test_moderate_signal_routes_to_advisor() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("Compare these two approaches")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is True


def test_routine_prompt_no_advisor() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("What's on my calendar today?")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is False


def test_sonnet_override_no_advisor() -> None:
    router = Router()
    model, thinking, use_advisor = router.choose_model("Find email from Sarah")
    assert model == "claude-sonnet-4-6"
    assert use_advisor is False


def test_advisor_disabled_routes_to_opus() -> None:
    original = defaults.ADVISOR_ENABLED
    defaults.ADVISOR_ENABLED = False
    try:
        router = Router()
        model, thinking, use_advisor = router.choose_model("What's our strategy?")
        assert model == "claude-opus-4-6"
        assert use_advisor is False
        assert thinking is not None  # adaptive thinking
    finally:
        defaults.ADVISOR_ENABLED = original


def test_strip_advisor_blocks_removes_advisor_content() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me think..."},
                {"type": "server_tool_use", "id": "x", "name": "advisor"},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "advisor_tool_result",
                    "tool_use_id": "x",
                    "content": "advice",
                },
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Based on the advice..."},
            ],
        },
    ]
    cleaned = _strip_advisor_blocks(messages)
    # First message: only text block remains
    assert len(cleaned[0]["content"]) == 1
    assert cleaned[0]["content"][0]["type"] == "text"
    # Second message: advisor_tool_result removed entirely (empty content filtered)
    assert len(cleaned) == 2
    # Last message: unchanged
    assert cleaned[-1]["content"][0]["text"] == "Based on the advice..."


def test_estimate_cost_basic() -> None:
    cost = estimate_cost("claude-sonnet-4-6", 1000, 500)
    expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
    assert abs(cost - expected) < 0.0001


def test_estimate_cost_with_advisor_mixed_models() -> None:
    iterations = [
        {"type": "message", "input_tokens": 1000, "output_tokens": 100},
        {
            "type": "advisor_message",
            "model": "claude-opus-4-6",
            "input_tokens": 500,
            "output_tokens": 200,
        },
        {"type": "message", "input_tokens": 800, "output_tokens": 300},
    ]
    cost = estimate_cost_with_advisor("claude-sonnet-4-6", iterations)
    # Sonnet: (1000+800)/1M * 3 + (100+300)/1M * 15 = 0.0054 + 0.006 = 0.0114
    # Opus: 500/1M * 15 + 200/1M * 75 = 0.0075 + 0.015 = 0.0225
    # Total: ~0.0339
    assert cost > 0.03
    assert cost < 0.04
