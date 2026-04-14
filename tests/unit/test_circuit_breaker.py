from __future__ import annotations

import time
from unittest.mock import MagicMock

from cosinabox.agent import loop as loop_module
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router


def _reset_breaker() -> None:
    loop_module._consecutive_failures = 0
    loop_module._last_failure_at = 0.0


def _build_loop(failing_client: MagicMock) -> AgentLoop:
    return AgentLoop(
        anthropic_client=failing_client,
        router=Router(),
        cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
        tools={},
        max_tool_iterations=1,
    )


def test_circuit_breaker_trips_after_threshold() -> None:
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = Exception("API down")
    loop = _build_loop(client)

    # Trigger 5 failures
    for _ in range(5):
        loop.run(prompt="hello", session_id="s")

    # 6th call should short-circuit
    client.messages.create.reset_mock()
    result = loop.run(prompt="hello", session_id="s")
    assert result.stopped_reason == "circuit_breaker"
    # No API call was made — breaker short-circuited
    assert client.messages.create.call_count == 0


def test_circuit_breaker_resets_after_cooldown() -> None:
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = Exception("API down")
    loop = _build_loop(client)

    for _ in range(5):
        loop.run(prompt="hello", session_id="s")

    # Simulate 11 minutes elapsed (cooldown is 10 min)
    loop_module._last_failure_at = time.time() - 700

    # Prepare a successful response for the next call
    fake_resp = MagicMock()
    fake_resp.stop_reason = "end_turn"
    fake_resp.content = [MagicMock(type="text", text="ok")]
    fake_resp.usage.input_tokens = 10
    fake_resp.usage.output_tokens = 5
    client.messages.create.side_effect = None
    client.messages.create.return_value = fake_resp

    result = loop.run(prompt="hello", session_id="s")
    # Breaker should have reset, call should have happened
    assert result.stopped_reason == "end_turn"
    assert loop_module._consecutive_failures == 0


def test_circuit_breaker_stays_tripped_within_cooldown() -> None:
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = Exception("API down")
    loop = _build_loop(client)

    for _ in range(5):
        loop.run(prompt="hello", session_id="s")

    # Still within cooldown window (just now)
    client.messages.create.reset_mock()
    result = loop.run(prompt="hello", session_id="s")
    assert result.stopped_reason == "circuit_breaker"
    assert client.messages.create.call_count == 0
