"""MCP `consult` endpoint for cosinabox.

This package exposes the Chief of Staff as a callable MCP tool so external
AI clients (Claude Code, Cowork, etc.) can consult the CoS without going
through Telegram. Shipped as the optional `consult` extra — installing
`cosinabox[consult]` pulls in the `mcp` Python SDK.

Milestone 1 only wires the rate limiter + metrics. The handler, prompts,
and MCP server land in subsequent milestones of
`docs/plans/2026-04-20-port-consult-mcp.md`.
"""

from cosinabox.consult.rate_limit import (
    RateLimiter,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)

__all__ = [
    "RateLimiter",
    "get_default_rate_limiter",
    "reset_default_rate_limiter",
]
