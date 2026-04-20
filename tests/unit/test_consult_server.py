"""Tests for the MCP consult server factory.

Exercises ``build_consult_server`` with injected fake ``HandlerDeps`` — no
real Anthropic calls, no real memory backend, no network. The tests mirror
the contract documented in M4 of
``docs/plans/2026-04-20-port-consult-mcp.md``:

- Two tools registered: ``consult`` and ``brainstorm``, each with a
  non-empty OSS-safe description.
- Happy path: tool invocation drives the handler with the expected mode and
  returns the handler's ``response`` text.
- Error path: a ``ConsultError`` from the handler is formatted as
  ``"[code] message"`` rather than raised.
- HTTP transport without ``CONSULT_API_KEY`` raises at factory time with a
  clear message.
- Memory adapter: joins a ``list[dict]`` with ``"\\n---\\n"`` and returns
  ``None`` on empty.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cosinabox.agent.cost import CostTracker
from cosinabox.agent.routing import Router
from cosinabox.consult import (
    ConsultError,
    ConsultResponse,
    Metrics,
    Persona,
    RateLimiter,
)
from cosinabox.consult.server import (
    HandlerDeps,
    MemoryClientAdapter,
    build_consult_server,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_persona() -> Persona:
    return Persona(
        name="Ada",
        timezone="UTC",
        personality="Founder.",
        consult_brainstorm_override=None,
    )


def _make_deps(*, response: ConsultResponse | ConsultError | None = None) -> HandlerDeps:
    """Return a HandlerDeps bundle with all collaborators mocked."""
    memory_client = MagicMock()
    memory_client.recall.return_value = None  # adapter-style: pre-joined str
    anthropic_client = MagicMock()
    cost_tracker = MagicMock(spec=CostTracker)
    return HandlerDeps(
        memory_client=memory_client,
        anthropic_client=anthropic_client,
        cost_tracker=cost_tracker,
        router=Router(),
        persona=_make_persona(),
        rate_limiter=RateLimiter(limit=30),
        metrics=Metrics(),
    )


# ---------------------------------------------------------------------------
# Server factory — tool registration
# ---------------------------------------------------------------------------


def test_build_consult_server_registers_two_tools(tmp_path: Path) -> None:
    deps = _make_deps()

    server = build_consult_server(tmp_path, handler_deps=deps)

    tools = asyncio.run(server.list_tools())
    names = sorted(t.name for t in tools)
    assert names == ["brainstorm", "consult"]
    for tool in tools:
        assert tool.description is not None
        assert tool.description.strip(), f"tool {tool.name} has empty description"


def test_tool_descriptions_are_oss_safe(tmp_path: Path) -> None:
    """Tool descriptions must not hardcode a specific user or company name.

    Per CLAUDE.md engine rule 1 ("no hardcoded names, orgs, or domains"),
    descriptions are generic. We guard against the most common accidents:
    Cowork (the original cos-agent client), the maintainer's name/org, or
    any placeholder that looks company-specific.
    """
    deps = _make_deps()
    server = build_consult_server(tmp_path, handler_deps=deps)

    tools = asyncio.run(server.list_tools())
    forbidden = ("Cowork", "cowork", "Rovik", "Keevs", "cosinabox user", "example.com")
    for tool in tools:
        desc = tool.description or ""
        for bad in forbidden:
            assert bad not in desc, (
                f"tool {tool.name!r} description contains forbidden token {bad!r}: {desc!r}"
            )


# ---------------------------------------------------------------------------
# Tool invocation drives the handler
# ---------------------------------------------------------------------------


def test_consult_tool_invokes_handler_with_consult_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = _make_deps()
    captured: dict[str, Any] = {}

    def fake_handle(req: Any, **kwargs: Any) -> ConsultResponse:
        captured["mode"] = req.mode
        captured["prompt"] = req.prompt
        captured["context"] = req.context
        return ConsultResponse(
            response="grounded answer",
            model_used="claude-sonnet-4-6",
            cost_usd=0.01,
            memory_hits=0,
            latency_ms=12,
        )

    monkeypatch.setattr("cosinabox.consult.server.handle_consult", fake_handle)
    server = build_consult_server(tmp_path, handler_deps=deps)

    result = asyncio.run(server.call_tool("consult", {"prompt": "why?"}))

    assert captured["mode"] == "consult"
    assert captured["prompt"] == "why?"
    assert captured["context"] is None
    # FastMCP returns a (content_blocks, structured) tuple for structured
    # outputs; the string lives in structured["result"].
    _blocks, structured = result
    assert structured == {"result": "grounded answer"}


def test_brainstorm_tool_invokes_handler_with_brainstorm_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = _make_deps()
    captured: dict[str, Any] = {}

    def fake_handle(req: Any, **kwargs: Any) -> ConsultResponse:
        captured["mode"] = req.mode
        return ConsultResponse(
            response="adversarial take",
            model_used="claude-opus-4-6",
            cost_usd=0.05,
            memory_hits=1,
            latency_ms=25,
        )

    monkeypatch.setattr("cosinabox.consult.server.handle_consult", fake_handle)
    server = build_consult_server(tmp_path, handler_deps=deps)

    result = asyncio.run(server.call_tool("brainstorm", {"prompt": "ship now or wait?"}))

    assert captured["mode"] == "brainstorm"
    _blocks, structured = result
    assert structured == {"result": "adversarial take"}


def test_consult_tool_formats_error_as_bracketed_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ConsultError from the handler is returned as ``[code] message`` —
    never raised — so MCP clients get structured text they can surface."""
    deps = _make_deps()

    def fake_handle(req: Any, **kwargs: Any) -> ConsultError:
        return ConsultError(error="too many calls this hour", code="rate_limited")

    monkeypatch.setattr("cosinabox.consult.server.handle_consult", fake_handle)
    server = build_consult_server(tmp_path, handler_deps=deps)

    _blocks, structured = asyncio.run(server.call_tool("consult", {"prompt": "why?"}))

    assert structured == {"result": "[rate_limited] too many calls this hour"}


def test_consult_tool_forwards_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _make_deps()
    captured: dict[str, Any] = {}

    def fake_handle(req: Any, **kwargs: Any) -> ConsultResponse:
        captured["context"] = req.context
        return ConsultResponse(
            response="ok", model_used="m", cost_usd=0.0, memory_hits=0, latency_ms=0
        )

    monkeypatch.setattr("cosinabox.consult.server.handle_consult", fake_handle)
    server = build_consult_server(tmp_path, handler_deps=deps)

    asyncio.run(
        server.call_tool("consult", {"prompt": "why?", "context": "we're in a design review"})
    )

    assert captured["context"] == "we're in a design review"


# ---------------------------------------------------------------------------
# Bearer auth / CONSULT_API_KEY policy
# ---------------------------------------------------------------------------


def test_empty_api_key_raises_at_factory_time(tmp_path: Path) -> None:
    deps = _make_deps()

    with pytest.raises(ValueError) as excinfo:
        build_consult_server(tmp_path, handler_deps=deps, api_key="", require_auth=True)

    msg = str(excinfo.value)
    assert "CONSULT_API_KEY" in msg
    assert "HTTP" in msg


def test_none_api_key_with_auth_required_raises(tmp_path: Path) -> None:
    deps = _make_deps()

    with pytest.raises(ValueError):
        build_consult_server(tmp_path, handler_deps=deps, api_key=None, require_auth=True)


def test_stdio_default_does_not_require_api_key(tmp_path: Path) -> None:
    """Stdio transport trusts the parent process — no api_key needed."""
    deps = _make_deps()

    # Should not raise — this is the default (stdio) path.
    server = build_consult_server(tmp_path, handler_deps=deps)
    assert server is not None


# ---------------------------------------------------------------------------
# Memory adapter
# ---------------------------------------------------------------------------


def test_memory_adapter_joins_entries_with_separator() -> None:
    mock_client = MagicMock()
    mock_client.recall.return_value = [{"text": "A"}, {"text": "B"}]

    adapter = MemoryClientAdapter(mock_client)
    result = adapter.recall("some query", namespace="Ada", limit=3)

    assert result == "A\n---\nB"
    mock_client.recall.assert_called_once_with(query="some query", namespace="Ada", limit=3)


def test_memory_adapter_empty_list_returns_none() -> None:
    mock_client = MagicMock()
    mock_client.recall.return_value = []

    adapter = MemoryClientAdapter(mock_client)
    result = adapter.recall("q", namespace="ns", limit=3)

    assert result is None


def test_memory_adapter_skips_entries_without_text() -> None:
    """Defensive: a future memory row without ``text`` shouldn't crash."""
    mock_client = MagicMock()
    mock_client.recall.return_value = [
        {"text": "A"},
        {"metadata": "no text here"},
        {"text": "B"},
    ]

    adapter = MemoryClientAdapter(mock_client)
    result = adapter.recall("q", namespace="ns", limit=3)

    assert result == "A\n---\nB"


def test_memory_adapter_single_entry_no_separator() -> None:
    mock_client = MagicMock()
    mock_client.recall.return_value = [{"text": "just one"}]

    adapter = MemoryClientAdapter(mock_client)
    result = adapter.recall("q", namespace="ns", limit=3)

    assert result == "just one"
