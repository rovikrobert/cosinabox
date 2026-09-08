"""Model-chain failover for the Anthropic API call.

Ported from cos-agent (`agent_failover.py`) 2026-04-17. cos-agent has
6 months of production use walking Opus → Sonnet → Haiku on 429/529/
overloaded; porting lifts cosinabox's reliability without new design.

Differences vs cos-agent:
  - Synchronous (cosinabox's agent loop is sync at the API-call layer).
  - No circuit-breaker state here — cosinabox's breaker lives in
    `cosinabox.agent.loop` and wraps this call.
  - `MODEL_FAILOVER_CHAIN` comes from `cosinabox.defaults`.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from cosinabox.agent.loop import _ADVISOR_BETA, _ADVISOR_TOOL
from cosinabox.defaults import MODEL_FAILOVER_CHAIN

logger = logging.getLogger(__name__)


def call_with_failover(
    client: Any,
    model: str,
    *,
    system: Any,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    thinking: dict[str, Any] | None = None,
    use_advisor: bool = False,
) -> tuple[Any, str]:
    """Call the Anthropic API, cascading through the failover chain on 429/529.

    Returns ``(response, model_actually_used)`` so cost tracking stays accurate.
    When ``use_advisor`` is True, injects the advisor tool and uses the beta
    API — except on Haiku fallback, where advisor (and extended thinking) are
    stripped because Haiku doesn't support them.

    Raises ``anthropic.APIError`` on unrecoverable errors (401 auth,
    "credit balance too low") or after the whole chain is exhausted.
    """
    try:
        start_idx = MODEL_FAILOVER_CHAIN.index(model)
        chain: tuple[str, ...] = MODEL_FAILOVER_CHAIN[start_idx:]
    except ValueError:
        chain = (model,)

    last_error: anthropic.APIError | None = None
    advisor_active = use_advisor

    for candidate in chain:
        is_haiku = "haiku" in candidate
        # Haiku doesn't support extended thinking or advisor.
        call_thinking = None if is_haiku else thinking
        if is_haiku:
            advisor_active = False

        call_tools = list(tools)
        if advisor_active:
            call_tools.append(_ADVISOR_TOOL)

        call_kwargs: dict[str, Any] = {
            "model": candidate,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            call_kwargs["system"] = system
        if call_tools:
            call_kwargs["tools"] = call_tools
        if call_thinking:
            call_kwargs["thinking"] = call_thinking

        try:
            if advisor_active:
                response = client.beta.messages.create(
                    betas=[_ADVISOR_BETA],
                    **call_kwargs,
                )
            else:
                response = client.messages.create(**call_kwargs)
        except anthropic.APIError as exc:
            last_error = exc
            msg = str(exc)
            status = getattr(exc, "status_code", None)

            # Unrecoverable — never try next model.
            if "credit balance is too low" in msg:
                raise
            if status == 401 or "authentication" in msg.lower():
                raise

            if status in (429, 529) or "overloaded" in msg or "rate_limit" in msg:
                logger.warning(
                    "Failover: %s failed with %s, trying next model",
                    candidate,
                    status,
                )
            else:
                logger.warning(
                    "Failover: %s failed with %s, trying next",
                    candidate,
                    msg[:100],
                )
            continue

        if candidate != model:
            logger.info("Failover: responded on %s (requested %s)", candidate, model)
        return response, candidate

    assert last_error is not None  # chain is non-empty; fall-through means we errored
    raise last_error


def call_with_failover_stream(
    client: Any,
    model: str,
    *,
    system: Any,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Streamed sibling of `call_with_failover`, returning accumulated text.

    Streaming exists here for one reason: a non-streamed call must declare a
    `max_tokens` it will not exceed, and a long structured response silently
    truncates against it. Streaming lets the ceiling be set generously without
    risking a mid-object cut, which is what corrupted two weekly digests in the
    legacy implementation.

    Returns `(text, model_actually_used)` so the caller can attribute cost.
    Raises `anthropic.APIError` once the whole chain is exhausted.
    """
    try:
        start_idx = MODEL_FAILOVER_CHAIN.index(model)
        chain: tuple[str, ...] = MODEL_FAILOVER_CHAIN[start_idx:]
    except ValueError:
        chain = (model,)

    last_error: Exception | None = None
    for candidate in chain:
        kwargs: dict[str, Any] = {
            "model": candidate,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            chunks: list[str] = []
            with client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    chunks.append(chunk)
            return "".join(chunks), candidate
        except anthropic.APIError as exc:
            last_error = exc
            status = getattr(exc, "status_code", None)
            message = str(exc)
            retryable = status in (429, 529) or "overloaded" in message.lower()
            if not retryable:
                raise
            logger.warning(
                "Streamed call to %s failed (%s) — trying next in chain", candidate, status
            )

    assert last_error is not None
    raise last_error
