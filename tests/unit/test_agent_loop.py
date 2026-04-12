from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("cosinabox.agent.loop.time.sleep", lambda *_: None)


def make_loop(anthropic_responses: list, tools: dict | None = None) -> AgentLoop:
    client = MagicMock()
    client.messages.create.side_effect = anthropic_responses
    return AgentLoop(
        anthropic_client=client,
        router=Router(available_tools=set(tools.keys()) if tools else set()),
        cost_tracker=CostTracker(per_message_cap_usd=10, daily_cap_usd=100),
        tools=tools or {},
        max_tool_iterations=8,
    )


def _text_response(text: str):
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    return resp


def _tool_call_response(name: str, tool_use_id: str, args: dict):
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    # NOTE: `name` is a reserved MagicMock constructor kwarg (sets the mock's
    # display name, not the .name attribute), so we must set .name explicitly.
    block = MagicMock(type="tool_use", id=tool_use_id, input=args)
    block.name = name
    resp.content = [block]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    return resp


def test_text_only_response_returns_immediately() -> None:
    loop = make_loop([_text_response("Hello!")])
    result = loop.run(prompt="hi", session_id="s1")
    assert result.final_text == "Hello!"
    assert result.tool_calls == []


def test_single_tool_call_then_final_text() -> None:
    fake_tool = MagicMock(return_value="It is sunny.")
    loop = make_loop(
        [
            _tool_call_response("weather", "tu_1", {"city": "SF"}),
            _text_response("The weather in SF is sunny."),
        ],
        tools={"weather": fake_tool},
    )
    result = loop.run(prompt="weather in SF?", session_id="s1")
    fake_tool.assert_called_once_with(city="SF")
    assert result.final_text == "The weather in SF is sunny."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "weather"


def test_max_iterations_breaks_loop() -> None:
    loop = make_loop(
        [_tool_call_response("noop", f"tu_{i}", {}) for i in range(10)],
        tools={"noop": MagicMock(return_value="ok")},
    )
    loop.max_tool_iterations = 3
    result = loop.run(prompt="loop forever", session_id="s1")
    assert result.stopped_reason == "max_iterations"
    assert len(result.tool_calls) == 3
