"""MCP `consult` endpoint for cosinabox.

This package exposes the Chief of Staff as a callable MCP tool so external
AI clients (Claude Code, Cowork, etc.) can consult the CoS without going
through Telegram. Shipped as the optional `consult` extra — installing
`cosinabox[consult]` pulls in the `mcp` Python SDK.

Milestone 1 only wires the rate limiter + metrics. The handler, prompts,
and MCP server land in subsequent milestones of
`docs/plans/2026-04-20-port-consult-mcp.md`.
"""

from cosinabox.consult.handler import (
    ConsultError,
    ConsultRequest,
    ConsultResponse,
    Persona,
    handle_consult,
    persona_from_config,
)
from cosinabox.consult.metrics import (
    Metrics,
    get_default_metrics,
    reset_default_metrics,
)
from cosinabox.consult.prompts import build_consult_system_prompt
from cosinabox.consult.rate_limit import (
    RateLimiter,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)

__all__ = [
    "ConsultError",
    "ConsultRequest",
    "ConsultResponse",
    "Metrics",
    "Persona",
    "RateLimiter",
    "build_consult_system_prompt",
    "get_default_metrics",
    "get_default_rate_limiter",
    "handle_consult",
    "persona_from_config",
    "reset_default_metrics",
    "reset_default_rate_limiter",
]
