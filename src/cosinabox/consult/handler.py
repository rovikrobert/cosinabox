"""Consult MCP endpoint handler.

Pure, sync business logic for a single consult call. Transport (stdio/HTTP)
and auth live in the MCP server layer (M4) — this module assumes the caller
is authorized.

Mirrors the semantics of cos-agent `consult.py` (no tools, memory recall,
best-effort cost record, in-memory metrics) while adapting to cosinabox's
dependency-injection style: every collaborator is a parameter, so unit
tests exercise the handler without touching the filesystem, the Anthropic
API, or the real memory backend.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cosinabox import defaults
from cosinabox.agent.cost import CostExceeded, CostTracker, estimate_cost
from cosinabox.agent.routing import Router
from cosinabox.consult.metrics import Metrics
from cosinabox.consult.prompts import build_consult_system_prompt
from cosinabox.consult.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ConsultRequest:
    """A single consult call — prompt + optional caller context + mode."""

    prompt: str
    context: str | None
    mode: str  # "consult" | "brainstorm"


@dataclass
class ConsultResponse:
    """Successful consult result."""

    response: str
    model_used: str
    cost_usd: float
    memory_hits: int
    latency_ms: int


@dataclass
class ConsultError:
    """Non-successful consult result.

    `code` is a stable machine-readable reason. The transport layer maps
    these to HTTP status codes / MCP error content.
    """

    error: str
    code: str  # "rate_limited" | "prompt_too_long" | "claude_error" | "invalid_mode"


@dataclass
class Persona:
    """Minimal persona shape the handler needs.

    The existing ``cosinabox.app.config.load_personality()`` returns a
    plain tuple ``(body, name, timezone)`` that doesn't carry the optional
    ``consult_brainstorm_override`` key added in schema v2. Rather than
    reshape that public tuple (which many callers rely on) we add a thin
    local dataclass and a ``persona_from_config`` adapter below. That
    keeps the handler's input contract explicit without duplicating the
    frontmatter-parsing logic.
    """

    name: str
    timezone: str
    personality: str
    consult_brainstorm_override: str | None = None


class MemoryRecaller(Protocol):
    """The recall contract the handler depends on.

    cos-agent's memory service returns a pre-joined ``str | None`` where
    memory separators are ``"\\n---\\n"`` — that's the shape the handler
    was designed for, and the shape we preserve here. The MCP server layer
    (M4) is responsible for wrapping a raw ``cosinabox.memory.MemoryClient``
    in an adapter that formats results as a joined string. Keeping that
    adapter out of the handler lets unit tests pass the string directly.
    """

    def recall(self, query: str, *, namespace: str, limit: int) -> str | None: ...


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def persona_from_config(config_dir: Path) -> Persona:
    """Build a :class:`Persona` from ``personality.md`` in ``config_dir``.

    Thin adapter on top of ``cosinabox.app.config.load_personality`` +
    ``load_personality_frontmatter`` — we re-parse the frontmatter only to
    pick up the optional ``consult_brainstorm_override`` key that the
    tuple API doesn't surface.
    """
    # Imported lazily so the handler module itself doesn't force-load yaml
    # for callers that pass a Persona directly.
    from cosinabox.app.config import load_personality, load_personality_frontmatter

    body, name, timezone = load_personality(config_dir)
    frontmatter = load_personality_frontmatter(config_dir)
    override = frontmatter.get("consult_brainstorm_override")
    if override is not None and not isinstance(override, str):
        # The schema allows string only — reject anything else loudly so a
        # misconfigured persona doesn't silently fall back to the default.
        raise ValueError(
            f"consult_brainstorm_override must be a string, got {type(override).__name__}"
        )
    return Persona(
        name=name,
        timezone=timezone,
        personality=body,
        consult_brainstorm_override=override,
    )


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


_VALID_MODES = ("consult", "brainstorm")


def handle_consult(
    req: ConsultRequest,
    *,
    memory_client: MemoryRecaller,
    anthropic_client: Any,
    cost_tracker: CostTracker,
    router: Router,
    persona: Persona,
    rate_limiter: RateLimiter,
    metrics: Metrics,
) -> ConsultResponse | ConsultError:
    """Process one consult call end-to-end.

    Order of checks matters:

    1. Invalid mode — fail fast, no side effects.
    2. Prompt-size guard — fail before consuming a rate-limit slot (we don't
       want a pathological caller to burn quota with 10MB prompts).
    3. Rate limit — consume a slot; once consumed, we commit to the call
       even if Claude errors below (matches cos-agent: "intent was counted").
    4. Memory recall — best-effort, failure logs at debug and continues.
    5. Build prompts (system + user) with the recalled block / override.
    6. Pick model (default for ``consult``, router for ``brainstorm``).
    7. Claude call with a monotonic timer.
    8. Cost record — best-effort; a cost-cap trip does not fail the request
       (the API call already happened, we've already paid).
    9. Metrics record + return.
    """
    # 1. Invalid mode first — no rate-limit burn, no anthropic call.
    if req.mode not in _VALID_MODES:
        return ConsultError(
            error=f"unknown consult mode: {req.mode!r}",
            code="invalid_mode",
        )

    # 2. Input size — same boundary as cos-agent (10,000 chars). Check before
    #    consuming the rate-limit slot so abusive callers don't also eat
    #    quota.
    total_len = len(req.prompt) + len(req.context or "")
    if total_len > defaults.CONSULT_MAX_PROMPT_CHARS:
        return ConsultError(
            error=(
                f"prompt too long (max {defaults.CONSULT_MAX_PROMPT_CHARS} chars, got {total_len})"
            ),
            code="prompt_too_long",
        )

    # 3. Rate limit — consume a slot or refuse.
    if not rate_limiter.allow():
        return ConsultError(error="rate limit exceeded", code="rate_limited")

    # 4. Memory recall — best-effort. Any exception (network, backend,
    #    schema mismatch) degrades to "no memories" rather than failing the
    #    call. The handler is meant to still answer even if memory is down.
    recalled: str | None
    try:
        recalled = memory_client.recall(
            req.prompt,
            namespace=persona.name,
            limit=3,
        )
    except Exception:
        logger.debug("Memory recall failed for consult", exc_info=True)
        recalled = None

    # 5. Build system prompt (+ optional recalled block, + optional
    #    brainstorm override).
    system_prompt = build_consult_system_prompt(
        personality=persona.personality,
        name=persona.name,
        timezone=persona.timezone,
        recalled=recalled,
        mode=req.mode,
        override_text=persona.consult_brainstorm_override,
    )

    # 6. User message — prefix caller-supplied context with an OSS-safe
    #    label (cos-agent said "COWORK SESSION"; we generalise to
    #    "CALLING SESSION" so the engine doesn't leak one specific client's
    #    branding).
    if req.context:
        user_message = (
            f"CONTEXT FROM CALLING SESSION:\n{req.context}\n\nQUESTION/IDEA:\n{req.prompt}"
        )
    else:
        user_message = req.prompt

    # 7. Model pick. ``consult`` is always the configured default so a
    #    predictable cost ceiling applies. ``brainstorm`` routes through the
    #    usual router so strategic prompts can escalate to Opus.
    if req.mode == "consult":
        model = defaults.CONSULT_DEFAULT_MODEL
    else:
        model, _thinking, _use_advisor = router.choose_model(
            prompt=req.prompt,
            conversation_context=None,
        )

    # 8. Claude call — timed. No tools (both modes are strictly no-tool).
    start = time.monotonic()
    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=defaults.CONSULT_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        # Broad catch: anthropic's exception tree is large, and tests need
        # to synthesize failures without instantiating an APIError. The
        # transport layer re-maps this to a 503 for HTTP callers.
        logger.exception("Consult Claude API call failed")
        return ConsultError(
            error=f"Claude API error: {type(exc).__name__}",
            code="claude_error",
        )
    latency_ms = (time.monotonic() - start) * 1000

    # 9. Extract text — concatenate every text-bearing content block, same
    #    as cos-agent. ``hasattr`` rather than ``type == "text"`` so tests
    #    using MagicMock don't need to configure block types.
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # 10. Cost estimate + best-effort record. A cost-cap trip here means the
    #     daily budget is blown — we still return the response because the
    #     API call already succeeded, and failing the caller would hide the
    #     partial work they're about to be billed for anyway.
    usage = response.usage
    cost = estimate_cost(
        model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
    try:
        cost_tracker.record(cost)
    except CostExceeded:
        logger.debug("Consult cost-cap exceeded during best-effort record", exc_info=True)
    except Exception:
        logger.debug("Failed to record consult cost", exc_info=True)

    # 11. Metrics.
    metrics.record(cost_usd=cost, latency_ms=latency_ms)

    # 12. memory_hits — cos-agent convention: count the ``\n---\n``
    #     separators and add one, so a single memory counts as 1 and two
    #     joined memories count as 2. Falsy recalled → 0.
    memory_hits = recalled.count("\n---\n") + 1 if recalled else 0

    return ConsultResponse(
        response=text,
        model_used=model,
        cost_usd=round(cost, 4),
        memory_hits=memory_hits,
        latency_ms=int(latency_ms),
    )
