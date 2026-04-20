"""Circuit breaker must only count Anthropic API errors, not tool errors.

Bug: the except block in agent/loop.py catches ALL exceptions, so a
google.auth.exceptions.RefreshError from a tool call increments the
circuit breaker. After 5 consecutive Google failures, ALL API calls
(including pure DM responses) are blocked.

Fix: catch anthropic.APIError for circuit breaker; catch other exceptions
separately and do NOT increment the counter.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
from google.auth.exceptions import RefreshError

from cosinabox.agent import loop as loop_module
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router


def _reset_breaker() -> None:
    loop_module._consecutive_failures = 0
    loop_module._last_failure_at = 0.0


def _build_loop(client: MagicMock) -> AgentLoop:
    return AgentLoop(
        anthropic_client=client,
        router=Router(),
        cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
        tools={},
        max_tool_iterations=1,
    )


def test_anthropic_api_error_trips_circuit_breaker() -> None:
    """anthropic.APIError 5x -> circuit breaker trips."""
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIError(
        message="server error", request=None, body=None
    )
    loop = _build_loop(client)

    for _ in range(5):
        loop.run(prompt="hello", session_id="s")

    assert loop_module._consecutive_failures >= 5

    # 6th call short-circuits without calling the API
    client.messages.create.reset_mock()
    result = loop.run(prompt="hello", session_id="s")
    assert result.stopped_reason == "circuit_breaker"
    assert client.messages.create.call_count == 0


def test_google_refresh_error_does_not_trip_circuit_breaker() -> None:
    """google.auth.exceptions.RefreshError 10x -> circuit breaker stays open."""
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = RefreshError("token expired")
    loop = _build_loop(client)

    for _ in range(10):
        result = loop.run(prompt="hello", session_id="s")
        # Should return an error, but NOT trip the circuit breaker
        assert result.stopped_reason == "api_error"

    # Breaker must NOT be tripped — DMs still work
    assert loop_module._consecutive_failures == 0

    # Next call with a working client should succeed
    fake_resp = MagicMock()
    fake_resp.stop_reason = "end_turn"
    fake_resp.content = [MagicMock(type="text", text="ok")]
    fake_resp.usage.input_tokens = 10
    fake_resp.usage.output_tokens = 5
    client.messages.create.side_effect = None
    client.messages.create.return_value = fake_resp

    result = loop.run(prompt="hello", session_id="s")
    assert result.stopped_reason == "end_turn"


def test_generic_exception_does_not_trip_circuit_breaker() -> None:
    """A random Exception (e.g. httpx.HTTPStatusError) must not trip the breaker."""
    _reset_breaker()
    client = MagicMock()
    client.messages.create.side_effect = ConnectionError("network down")
    loop = _build_loop(client)

    for _ in range(10):
        result = loop.run(prompt="hello", session_id="s")
        assert result.stopped_reason == "api_error"

    assert loop_module._consecutive_failures == 0
