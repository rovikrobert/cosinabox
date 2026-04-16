"""Rela query tool — lets the CoS ask about relationship health in DM."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

RELA_QUERY_DEFINITION = {
    "name": "rela_query",
    "description": (
        "Ask the relationship manager about a stakeholder's health. "
        "Returns health score, trend, and recommendations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Question about a stakeholder (e.g., 'How is my relationship with Alice?')"
                ),
            },
        },
        "required": ["query"],
    },
}


def rela_query_handler(rela_agent: Any | None) -> Callable[..., str]:
    def handler(query: str) -> str:
        if rela_agent is None:
            return "Rela relationship manager not configured."
        try:
            return rela_agent.query(query)
        except Exception as exc:
            return f"Rela query failed: {exc}"

    return handler
