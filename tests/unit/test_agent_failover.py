"""Tests for `call_with_failover` — model-chain failover on 429/529.

Ported from cos-agent (`agent_failover.py`) — see
`docs/plans/2026-04-17-port-agent-failover.md`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest
from cosinabox.agent.failover import call_with_failover

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeAPIError(anthropic.APIError):
    """APIError that doesn't require an httpx.Request to construct."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        self.body = None
        # Bypass parent __init__ — it demands a real httpx.Request.

    def __str__(self) -> str:
        return self.message


def _fake_response() -> MagicMock:
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(type="text", text="ok")]
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    return resp


def _client(side_effects: list[object] | object) -> MagicMock:
    """Build a mock Anthropic client whose messages.create returns/raises."""
    client = MagicMock()
    if isinstance(side_effects, list):
        client.messages.create.side_effect = side_effects
        client.beta.messages.create.side_effect = side_effects
    else:
        client.messages.create.return_value = side_effects
        client.beta.messages.create.return_value = side_effects
    return client


_OPUS = "claude-opus-4-6"
_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def test_first_model_succeeds_no_failover() -> None:
    resp = _fake_response()
    client = _client(resp)

    got, used = call_with_failover(
        client,
        _OPUS,
        system=[{"type": "text", "text": "sys"}],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
    )

    assert got is resp
    assert used == _OPUS
    assert client.messages.create.call_count == 1
    assert client.beta.messages.create.call_count == 0


def test_rate_limit_falls_back_to_sonnet() -> None:
    resp = _fake_response()
    client = _client([_FakeAPIError("rate_limit", status_code=429), resp])

    got, used = call_with_failover(
        client,
        _OPUS,
        system=[],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
    )

    assert got is resp
    assert used == _SONNET
    assert client.messages.create.call_count == 2


def test_overloaded_falls_back() -> None:
    resp = _fake_response()
    client = _client([_FakeAPIError("Overloaded", status_code=529), resp])

    got, used = call_with_failover(
        client,
        _OPUS,
        system=[],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
    )

    assert got is resp
    assert used == _SONNET


def test_all_models_exhausted_raises() -> None:
    err = _FakeAPIError("rate_limit", status_code=429)
    client = _client([err, err, err])

    with pytest.raises(anthropic.APIError) as excinfo:
        call_with_failover(
            client,
            _OPUS,
            system=[],
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )

    assert excinfo.value.status_code == 429
    # Tried every model in the chain
    assert client.messages.create.call_count == 3


def test_unrecoverable_credit_error_raises_immediately() -> None:
    err = _FakeAPIError(
        "Your credit balance is too low to access the Anthropic API.",
        status_code=400,
    )
    client = _client([err])

    with pytest.raises(anthropic.APIError):
        call_with_failover(
            client,
            _OPUS,
            system=[],
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )

    # No failover attempted
    assert client.messages.create.call_count == 1


def test_401_auth_error_raises_immediately() -> None:
    err = _FakeAPIError("invalid x-api-key", status_code=401)
    client = _client([err])

    with pytest.raises(anthropic.APIError):
        call_with_failover(
            client,
            _OPUS,
            system=[],
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )

    assert client.messages.create.call_count == 1


def test_haiku_fallback_strips_advisor() -> None:
    # Opus + Sonnet fail via beta (advisor active); Haiku succeeds via non-beta
    # (advisor stripped). The beta and non-beta paths are separate mock
    # attributes with independent side_effect iterators.
    resp = _fake_response()
    client = MagicMock()
    client.beta.messages.create.side_effect = [
        _FakeAPIError("rate_limit", status_code=429),
        _FakeAPIError("rate_limit", status_code=429),
    ]
    client.messages.create.return_value = resp

    got, used = call_with_failover(
        client,
        _OPUS,
        system=[],
        tools=[{"name": "some_tool"}],
        messages=[{"role": "user", "content": "hi"}],
        use_advisor=True,
    )

    assert used == _HAIKU
    assert got is resp

    # Opus + Sonnet tried via beta (advisor active)
    assert client.beta.messages.create.call_count == 2
    # Haiku via non-beta (advisor stripped)
    assert client.messages.create.call_count == 1

    haiku_kwargs = client.messages.create.call_args.kwargs
    assert haiku_kwargs["model"] == _HAIKU
    # Advisor tool definition must not be in haiku's tools
    for t in haiku_kwargs["tools"]:
        assert t.get("name") != "advisor"


def test_haiku_fallback_strips_thinking() -> None:
    resp = _fake_response()
    client = _client(
        [
            _FakeAPIError("rate_limit", status_code=429),  # opus
            _FakeAPIError("rate_limit", status_code=429),  # sonnet
            resp,  # haiku
        ]
    )

    call_with_failover(
        client,
        _OPUS,
        system=[],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
        thinking={"type": "enabled", "budget_tokens": 1024},
    )

    # Haiku call must not include thinking kwarg
    haiku_kwargs = client.messages.create.call_args_list[-1].kwargs
    assert "thinking" not in haiku_kwargs


def test_failover_returns_actual_model_used() -> None:
    resp = _fake_response()
    client = _client([_FakeAPIError("rate_limit", status_code=429), resp])

    _, used = call_with_failover(
        client,
        _OPUS,
        system=[],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
    )

    # Not the requested model — the one that actually responded
    assert used == _SONNET
    assert used != _OPUS


def test_unknown_model_uses_single_item_chain() -> None:
    err = _FakeAPIError("rate_limit", status_code=429)
    client = _client([err])

    with pytest.raises(anthropic.APIError):
        call_with_failover(
            client,
            "claude-opus-9-9-future",
            system=[],
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )

    # Only the requested model was tried; no failover into the chain
    assert client.messages.create.call_count == 1
    assert client.messages.create.call_args.kwargs["model"] == "claude-opus-9-9-future"
