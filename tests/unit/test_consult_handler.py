"""Tests for the consult MCP endpoint handler.

The handler is sync (matches cosinabox house style) and takes all
dependencies as injected parameters — no module-level singletons inside the
handler itself. These tests verify the cos-agent `consult.py` semantics
port cleanly: rate limit, prompt-size guard, best-effort memory recall,
best-effort cost recording, and the two modes (`consult` / `brainstorm`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cosinabox import defaults
from cosinabox.agent.cost import CostExceeded, CostTracker
from cosinabox.agent.routing import Router
from cosinabox.consult import (
    ConsultError,
    ConsultRequest,
    ConsultResponse,
    Metrics,
    Persona,
    RateLimiter,
    handle_consult,
    persona_from_config,
)

# ---------------------------------------------------------------------------
# Helpers (mirror the test_agent_loop.py idiom)
# ---------------------------------------------------------------------------


def _text_response(
    text: str,
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> MagicMock:
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.usage.cache_creation_input_tokens = cache_creation_tokens
    resp.usage.cache_read_input_tokens = cache_read_tokens
    return resp


def _make_persona(
    *,
    name: str = "Ada",
    timezone: str = "UTC",
    personality: str = "Founder of a seed-stage startup.",
    consult_brainstorm_override: str | None = None,
) -> Persona:
    return Persona(
        name=name,
        timezone=timezone,
        personality=personality,
        consult_brainstorm_override=consult_brainstorm_override,
    )


def _make_deps(
    *,
    anthropic_responses: list[Any] | None = None,
    recall_return: Any = "fact A\n---\nfact B",
    recall_side_effect: Any = None,
    persona: Persona | None = None,
    rate_limit: int = 30,
    router: Router | None = None,
) -> dict[str, Any]:
    anthropic_client = MagicMock()
    if anthropic_responses is not None:
        anthropic_client.messages.create.side_effect = anthropic_responses

    memory_client = MagicMock()
    if recall_side_effect is not None:
        memory_client.recall.side_effect = recall_side_effect
    else:
        memory_client.recall.return_value = recall_return

    cost_tracker = MagicMock(spec=CostTracker)
    cost_tracker.record = MagicMock()

    return {
        "memory_client": memory_client,
        "anthropic_client": anthropic_client,
        "cost_tracker": cost_tracker,
        "router": router or Router(),
        "persona": persona or _make_persona(),
        "rate_limiter": RateLimiter(limit=rate_limit),
        "metrics": Metrics(),
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_handle_consult_happy_path() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("Here's the answer")])
    req = ConsultRequest(prompt="why?", context=None, mode="consult")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    assert result.response == "Here's the answer"
    assert result.model_used == defaults.CONSULT_DEFAULT_MODEL
    assert result.memory_hits == 2
    assert result.cost_usd > 0
    assert result.latency_ms >= 0

    # System prompt passed to anthropic contains the recalled memory.
    call_kwargs = deps["anthropic_client"].messages.create.call_args.kwargs
    assert "fact A" in call_kwargs["system"]
    assert "fact B" in call_kwargs["system"]

    # Side-effect assertions.
    assert deps["rate_limiter"].snapshot()["count"] == 1
    assert deps["metrics"].snapshot()["calls_today"] == 1
    assert deps["cost_tracker"].record.call_count == 1


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_rate_limit_blocks() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("unused")], rate_limit=1)
    # Pre-fill limiter to its limit.
    assert deps["rate_limiter"].allow() is True

    req = ConsultRequest(prompt="why?", context=None, mode="consult")
    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultError)
    assert result.code == "rate_limited"
    deps["anthropic_client"].messages.create.assert_not_called()


def test_prompt_too_long() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("unused")])
    req = ConsultRequest(
        prompt="x" * (defaults.CONSULT_MAX_PROMPT_CHARS + 1),
        context=None,
        mode="consult",
    )

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultError)
    assert result.code == "prompt_too_long"
    # Size check comes before rate-limit consumption.
    assert deps["rate_limiter"].snapshot()["count"] == 0
    deps["anthropic_client"].messages.create.assert_not_called()


def test_invalid_mode() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("unused")])
    req = ConsultRequest(prompt="why?", context=None, mode="xyz")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultError)
    assert result.code == "invalid_mode"
    # Invalid mode check comes first — nothing else advanced.
    assert deps["rate_limiter"].snapshot()["count"] == 0
    deps["anthropic_client"].messages.create.assert_not_called()


def test_memory_recall_raises_is_tolerated() -> None:
    deps = _make_deps(
        anthropic_responses=[_text_response("answer without memory")],
        recall_side_effect=RuntimeError("boom"),
    )
    req = ConsultRequest(prompt="why?", context=None, mode="consult")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    assert result.memory_hits == 0

    call_kwargs = deps["anthropic_client"].messages.create.call_args.kwargs
    assert "<recalled_memories>" not in call_kwargs["system"]


def test_claude_api_error() -> None:
    deps = _make_deps(anthropic_responses=None)
    deps["anthropic_client"].messages.create.side_effect = RuntimeError("api down")
    req = ConsultRequest(prompt="why?", context=None, mode="consult")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultError)
    assert result.code == "claude_error"
    assert "RuntimeError" in result.error
    # Metrics NOT recorded on API error — rate limiter IS advanced (intent counted).
    assert deps["metrics"].snapshot()["calls_today"] == 0
    assert deps["rate_limiter"].snapshot()["count"] == 1


def test_cost_cap_exceeded_does_not_fail_request() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("answer despite cap")])
    deps["cost_tracker"].record.side_effect = CostExceeded("daily cap hit")
    req = ConsultRequest(prompt="why?", context=None, mode="consult")

    result = handle_consult(req, **deps)

    # Request already completed; charging is best-effort.
    assert isinstance(result, ConsultResponse)
    assert result.response == "answer despite cap"
    assert deps["metrics"].snapshot()["calls_today"] == 1


# ---------------------------------------------------------------------------
# Brainstorm mode
# ---------------------------------------------------------------------------


def test_brainstorm_mode_uses_router() -> None:
    router = MagicMock(spec=Router)
    router.choose_model.return_value = ("claude-opus-4-6", None, False)

    deps = _make_deps(
        anthropic_responses=[_text_response("contrarian take")],
        router=router,
    )
    req = ConsultRequest(prompt="why?", context=None, mode="brainstorm")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    assert result.model_used == "claude-opus-4-6"
    assert router.choose_model.call_count == 1

    call_kwargs = deps["anthropic_client"].messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-6"
    # Default brainstorm override appears when persona provides no override.
    assert defaults.CONSULT_BRAINSTORM_OVERRIDE_DEFAULT in call_kwargs["system"]


def test_persona_brainstorm_override_wins() -> None:
    router = MagicMock(spec=Router)
    router.choose_model.return_value = ("claude-opus-4-6", None, False)

    persona = _make_persona(consult_brainstorm_override="Custom override XYZ")
    deps = _make_deps(
        anthropic_responses=[_text_response("contrarian take")],
        router=router,
        persona=persona,
    )
    req = ConsultRequest(prompt="why?", context=None, mode="brainstorm")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    call_kwargs = deps["anthropic_client"].messages.create.call_args.kwargs
    assert "Custom override XYZ" in call_kwargs["system"]
    assert defaults.CONSULT_BRAINSTORM_OVERRIDE_DEFAULT not in call_kwargs["system"]


# ---------------------------------------------------------------------------
# memory_hits counting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("recalled", "expected_hits"),
    [
        ("", 0),
        ("one", 1),
        ("one\n---\ntwo", 2),
        ("a\n---\nb\n---\nc", 3),
    ],
)
def test_memory_hits_counting(recalled: str, expected_hits: int) -> None:
    deps = _make_deps(
        anthropic_responses=[_text_response("answer")],
        recall_return=recalled,
    )
    req = ConsultRequest(prompt="why?", context=None, mode="consult")

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    assert result.memory_hits == expected_hits


# ---------------------------------------------------------------------------
# Context prefix
# ---------------------------------------------------------------------------


def test_context_is_prefixed_to_user_message() -> None:
    deps = _make_deps(anthropic_responses=[_text_response("answer")])
    req = ConsultRequest(
        prompt="why?",
        context="in design review",
        mode="consult",
    )

    result = handle_consult(req, **deps)

    assert isinstance(result, ConsultResponse)
    call_kwargs = deps["anthropic_client"].messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]

    assert "CONTEXT FROM CALLING SESSION:" in user_content
    assert "QUESTION/IDEA:" in user_content
    assert "in design review" in user_content
    assert "why?" in user_content
    # OSS-safe phrasing — no leaked cos-agent wording.
    assert "COWORK" not in user_content


# ---------------------------------------------------------------------------
# persona_from_config adapter
# ---------------------------------------------------------------------------


def test_persona_from_config_happy_path(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text(
        "---\n"
        "schema_version: 2\n"
        "name: Taylor\n"
        "timezone: America/Los_Angeles\n"
        'consult_brainstorm_override: "Argue against my framing from an eng-risk angle."\n'
        "---\n"
        "Founder of a seed-stage startup.\n"
    )

    persona = persona_from_config(tmp_path)

    assert persona.name == "Taylor"
    assert persona.timezone == "America/Los_Angeles"
    assert "Founder" in persona.personality
    assert persona.consult_brainstorm_override == (
        "Argue against my framing from an eng-risk angle."
    )


def test_persona_from_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    """Mirror load_personality: a missing file yields a fallback persona
    rather than raising, so `consult-serve` degrades loudly in logs but
    doesn't crash on startup."""
    persona = persona_from_config(tmp_path)

    assert persona.name == "user"
    assert persona.timezone == defaults.DEFAULT_TIMEZONE
    assert persona.personality == "(no personality)"
    assert persona.consult_brainstorm_override is None
