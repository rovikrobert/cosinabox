from __future__ import annotations

from types import SimpleNamespace

import anthropic
import pytest

from cosinabox.agent.failover import call_with_failover_stream
from cosinabox.defaults import MODEL_FAILOVER_CHAIN


class _FakeAPIError(anthropic.APIError):
    """APIError that doesn't require an httpx.Request to construct.

    Mirrors the helper in test_agent_failover.py. The plan's snippet built a
    real APIStatusError with a SimpleNamespace response, but the SDK's
    constructor dereferences `response.request`, so it raised AttributeError
    inside the test rather than exercising the failover path.
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        self.body = None

    def __str__(self) -> str:
        return self.message


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self):
        yield from self._chunks


def _client(behaviour):
    return SimpleNamespace(messages=SimpleNamespace(stream=behaviour))


def test_accumulates_the_streamed_text():
    client = _client(lambda **kw: _FakeStream(["Hello, ", "world", "!"]))
    text, model = call_with_failover_stream(
        client, MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=64_000
    )
    assert text == "Hello, world!"
    assert model == MODEL_FAILOVER_CHAIN[0]


def test_passes_max_tokens_and_system_through():
    seen: dict[str, object] = {}

    def _stream(**kw):
        seen.update(kw)
        return _FakeStream(["x"])

    call_with_failover_stream(
        _client(_stream),
        MODEL_FAILOVER_CHAIN[0],
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64_000,
    )
    assert seen["max_tokens"] == 64_000
    assert seen["system"] == "sys"
    assert seen["messages"] == [{"role": "user", "content": "hi"}]


def test_falls_through_the_chain_on_overload():
    attempts: list[str] = []

    def _stream(**kw):
        attempts.append(kw["model"])
        if len(attempts) == 1:
            raise _FakeAPIError("overloaded", status_code=529)
        return _FakeStream(["ok"])

    text, model = call_with_failover_stream(
        _client(_stream), MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=1000
    )
    assert text == "ok"
    assert attempts == list(MODEL_FAILOVER_CHAIN[:2])
    assert model == MODEL_FAILOVER_CHAIN[1]


def test_raises_after_the_chain_is_exhausted():
    def _stream(**kw):
        raise _FakeAPIError("overloaded", status_code=529)

    with pytest.raises(anthropic.APIError):
        call_with_failover_stream(
            _client(_stream), MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=1000
        )
