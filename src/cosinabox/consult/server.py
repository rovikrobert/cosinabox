"""MCP server factory for the cosinabox consult endpoint.

Wraps the pure sync :func:`cosinabox.consult.handler.handle_consult` in a
``FastMCP`` server exposing two tools (``consult`` and ``brainstorm``). The
same server factory supports stdio (parent-process trust) and HTTP
transports — on HTTP the caller must provide ``CONSULT_API_KEY`` so Bearer
auth is enforced via the SDK's ``TokenVerifier`` surface.

SDK vetting (2026-04-20, recorded in
``docs/plans/2026-04-20-port-consult-mcp.md`` — "M1 SDK vetting log"):

- SDK under test: ``mcp==1.27.0`` on PyPI
  (``from mcp.server.fastmcp import FastMCP``). Pin: ``mcp>=1.12``.
- API surface used:
    * ``@server.tool()`` decorator for tool registration.
    * ``server.run(transport="stdio" | "streamable-http" | "sse")`` — a
      single entry point; there are no ``run_stdio()`` / ``run_http()``
      methods in this SDK version.
    * ``server.list_tools()`` and ``server.call_tool(name, args)`` — both
      async; tests drive them via ``asyncio.run``.
- HTTP auth: the SDK ships OAuth 2.1 Resource Server primitives
  (``mcp.server.auth.provider.TokenVerifier`` +
  ``mcp.server.auth.settings.AuthSettings``). We use them as a degenerate
  shared-secret: a single ``CONSULT_API_KEY`` env var, compared in
  constant time via ``hmac.compare_digest``. Full OAuth is out of scope.
  ``AuthSettings.issuer_url`` / ``resource_server_url`` are required by
  the Pydantic model even when unused, so we supply local placeholders.

The handler expects a ``MemoryRecaller`` (pre-joined string) while
``cosinabox.memory.client.MemoryClient`` returns ``list[dict]`` — the
``MemoryClientAdapter`` below bridges the two, joining hit texts with
``"\\n---\\n"`` and returning ``None`` on empty so the handler's ``recall``
code path stays untouched.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anthropic
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from cosinabox import defaults
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.routing import Router
from cosinabox.consult.handler import (
    ConsultError,
    ConsultRequest,
    ConsultResponse,
    Persona,
    handle_consult,
    persona_from_config,
)
from cosinabox.consult.metrics import Metrics, get_default_metrics
from cosinabox.consult.rate_limit import RateLimiter, get_default_rate_limiter

__all__ = [
    "HandlerDeps",
    "MemoryClientAdapter",
    "build_consult_server",
]


# ---------------------------------------------------------------------------
# Dependency bundle
# ---------------------------------------------------------------------------


@dataclass
class HandlerDeps:
    """All collaborators ``handle_consult`` needs, bundled for injection.

    Production code calls :func:`build_consult_server` without
    ``handler_deps`` — the factory loads real deps from ``config_dir``.
    Tests pass a fully-mocked bundle to avoid filesystem / network.
    """

    memory_client: Any  # MemoryRecaller-compatible (recall -> str | None)
    anthropic_client: Any  # anthropic.Anthropic
    cost_tracker: CostTracker
    router: Router
    persona: Persona
    rate_limiter: RateLimiter
    metrics: Metrics


# ---------------------------------------------------------------------------
# Memory adapter
# ---------------------------------------------------------------------------


class MemoryClientAdapter:
    """Adapt a ``MemoryClient`` (list-of-dicts) to the ``MemoryRecaller``
    protocol (pre-joined string) the handler was built against.

    Kept inline in ``server.py`` per the plan ("keep it in server.py unless
    it grows beyond 30 lines"). At 20-odd lines this is small enough; if it
    ever grows non-trivial logic (ranking, filtering, dedup) it should move
    to ``memory_adapter.py``.
    """

    _SEPARATOR = "\n---\n"

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def recall(self, query: str, *, namespace: str, limit: int) -> str | None:
        hits = self._inner.recall(query=query, namespace=namespace, limit=limit)
        texts = [h["text"] for h in hits if isinstance(h, dict) and "text" in h]
        if not texts:
            return None
        return self._SEPARATOR.join(texts)


# ---------------------------------------------------------------------------
# Bearer auth (HTTP only)
# ---------------------------------------------------------------------------


class _SharedSecretVerifier(TokenVerifier):
    """Degenerate TokenVerifier: one valid token (``CONSULT_API_KEY``).

    Uses :func:`hmac.compare_digest` so a wrong prefix doesn't leak timing
    info. A match returns a placeholder ``AccessToken`` with the ``user``
    scope — enough for the SDK's middleware to accept the call. A mismatch
    returns ``None``, which the SDK maps to HTTP 401.
    """

    def __init__(self, expected: str) -> None:
        self._expected = expected

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        if hmac.compare_digest(token, self._expected):
            return AccessToken(
                token=token,
                client_id="consult-shared-secret",
                scopes=["user"],
                expires_at=None,
                resource=None,
            )
        return None


_AUTH_MISSING_MESSAGE = (
    "CONSULT_API_KEY must be set when binding to HTTP. "
    "Set it in .env or export it before running consult-serve."
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_consult_server(
    config_dir: Path,
    *,
    handler_deps: HandlerDeps | None = None,
    api_key: str | None = None,
    require_auth: bool = False,
) -> FastMCP:
    """Build a ``FastMCP`` server exposing ``consult`` + ``brainstorm``.

    ``handler_deps`` overrides the default dep loading — tests pass a
    fully-mocked bundle. In production, pass ``None`` and let the factory
    wire real collaborators from ``config_dir``.

    ``api_key`` is consulted only when ``require_auth=True`` (HTTP
    transport). An empty or ``None`` key with auth required raises at
    factory time with a clear message — failing loud beats silently binding
    an unauthenticated HTTP endpoint.
    """
    if require_auth:
        if not api_key:
            raise ValueError(_AUTH_MISSING_MESSAGE)
        verifier: TokenVerifier | None = _SharedSecretVerifier(api_key)
        auth: AuthSettings | None = AuthSettings(
            # Placeholder URLs — required by AuthSettings but irrelevant
            # for shared-secret flow. The SDK uses these for OAuth
            # discovery metadata; in our case no one queries them.
            issuer_url=cast(AnyHttpUrl, "http://localhost/consult"),
            resource_server_url=cast(AnyHttpUrl, "http://localhost/consult"),
            required_scopes=["user"],
        )
    else:
        verifier = None
        auth = None

    deps = handler_deps if handler_deps is not None else _load_default_deps(config_dir)

    server: FastMCP = FastMCP(
        "cosinabox-consult",
        token_verifier=verifier,
        auth=auth,
    )

    @server.tool(
        name="consult",
        description=(
            "Ask the configured Chief of Staff agent for grounded reasoning on a "
            "question. Returns a direct answer informed by the user's stored "
            "memory and stated priorities. No side effects — the agent does not "
            "call tools in this mode. Use for design reviews, prioritization "
            "questions, or any time you want a thoughtful take grounded in the "
            "user's own context."
        ),
    )
    def consult(prompt: str, context: str | None = None) -> str:
        req = ConsultRequest(prompt=prompt, context=context, mode="consult")
        return _run(deps, req)

    @server.tool(
        name="brainstorm",
        description=(
            "Ask the Chief of Staff agent to argue adversarially against your "
            "framing. Use this when you want your assumptions stress-tested, "
            "not validated. Returns a direct answer written from a skeptical "
            "stance. No side effects — the agent does not call tools in this "
            "mode."
        ),
    )
    def brainstorm(prompt: str, context: str | None = None) -> str:
        req = ConsultRequest(prompt=prompt, context=context, mode="brainstorm")
        return _run(deps, req)

    return server


def _run(deps: HandlerDeps, req: ConsultRequest) -> str:
    """Invoke the handler and coerce the result to a string.

    Happy path: the handler's ``response`` text. Error path: a bracketed
    ``[code] message`` string so MCP clients get structured error content
    rather than an exception (which would close the stdio pipe).
    """
    result = handle_consult(
        req,
        memory_client=deps.memory_client,
        anthropic_client=deps.anthropic_client,
        cost_tracker=deps.cost_tracker,
        router=deps.router,
        persona=deps.persona,
        rate_limiter=deps.rate_limiter,
        metrics=deps.metrics,
    )
    if isinstance(result, ConsultError):
        return f"[{result.code}] {result.error}"
    assert isinstance(result, ConsultResponse)
    return result.response


def _load_default_deps(config_dir: Path) -> HandlerDeps:
    """Build real ``HandlerDeps`` from ``config_dir``.

    Imported lazily inside the function so importing ``server`` for tests
    (which always inject fake deps) doesn't spin up cost trackers / memory
    clients / anthropic clients.
    """
    from cosinabox.memory.client import resolve_memory_client

    # Memory: local SQLite by default, remote if MEMORY_SERVICE_URL is set.
    raw_memory = resolve_memory_client(db_path=config_dir / "memory.db")
    memory_client = MemoryClientAdapter(raw_memory)

    # Anthropic client: reads ANTHROPIC_API_KEY from env (standard).
    anthropic_client = anthropic.Anthropic()

    # Cost tracker with engine defaults. No DB persistence here — consult
    # runs in a short-lived server process; per-day cost survives only in
    # the metrics snapshot (by design, per the scope doc "audit log — no").
    cost_tracker = CostTracker(
        per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
        daily_cap_usd=defaults.COST_DAILY_CAP_USD,
    )

    return HandlerDeps(
        memory_client=memory_client,
        anthropic_client=anthropic_client,
        cost_tracker=cost_tracker,
        router=Router(),
        persona=persona_from_config(config_dir),
        rate_limiter=get_default_rate_limiter(),
        metrics=get_default_metrics(),
    )


# ---------------------------------------------------------------------------
# ``python -m cosinabox.consult.server`` entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    """Minimal stdio entry point for integration tests / ad-hoc use.

    The public CLI (``cosinabox consult-serve``) lands in M5 with proper
    click options for transport, bind address, and HTTP auth. This entry
    point exists so an ``mcp.client.stdio`` subprocess can spawn the server
    without depending on the CLI package.

    If ``COSINABOX_CONSULT_STUB=1`` is set, we skip ``_load_default_deps``
    (which would require ``ANTHROPIC_API_KEY`` + a real memory DB + a
    parseable ``personality.md``) and substitute an in-process stub. This
    is used exclusively by ``tests/integration/test_consult_mcp_stdio.py``
    and must never be set in production.
    """
    config_dir = Path(os.environ.get("COSINABOX_CONFIG_DIR", "."))
    if os.environ.get("COSINABOX_CONSULT_STUB") == "1":
        deps = _build_stub_deps()
        server = build_consult_server(config_dir, handler_deps=deps)
    else:
        server = build_consult_server(config_dir)
    server.run(transport="stdio")


def _build_stub_deps() -> HandlerDeps:
    """Construct a stub dep bundle for integration tests.

    The stub wires a mock Anthropic client returning a fixed text block
    and a no-op memory recall. Consult tool calls flow through the real
    ``handle_consult`` pipeline (rate limit, prompt-size guard, metrics),
    so the integration test exercises real server↔handler glue without
    touching external services.
    """
    from unittest.mock import MagicMock

    anthropic_client = MagicMock()
    fake_response = MagicMock()
    fake_block = MagicMock()
    fake_block.text = "stubbed consult answer"
    fake_response.content = [fake_block]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.cache_read_input_tokens = 0
    anthropic_client.messages.create.return_value = fake_response

    memory_client = MagicMock()
    memory_client.recall.return_value = None

    persona = Persona(
        name="Stub",
        timezone="UTC",
        personality="Stubbed persona for integration tests.",
        consult_brainstorm_override=None,
    )

    return HandlerDeps(
        memory_client=memory_client,
        anthropic_client=anthropic_client,
        cost_tracker=CostTracker(
            per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
            daily_cap_usd=defaults.COST_DAILY_CAP_USD,
        ),
        router=Router(),
        persona=persona,
        rate_limiter=RateLimiter(limit=defaults.CONSULT_RATE_LIMIT_PER_HOUR),
        metrics=Metrics(),
    )


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    _main()
