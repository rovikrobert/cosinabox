"""Agent-facing tools for commitment CRUD.

Registered when a ``Memory`` instance is wired into the registry. Every
tool returns a short string (success marker or error message) so the
agent can summarize it back to the user without special-casing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cosinabox.commitments import (
    CommitmentAlreadyClosed,
    CommitmentNotClosed,
    CommitmentNotFound,
    close_commitment,
    create_commitment,
    dismiss_commitment,
    get_commitment,
    list_commitments,
    reopen_commitment,
    update_commitment,
)
from cosinabox.memory import Memory

COMMITMENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "commitment_create",
        "description": (
            "Record a new commitment (open work item). Use when the user says "
            "they'll do something, or when something a user must follow up on "
            "surfaces in a meeting or email. Priority 1 is highest. Deadline "
            "is optional ISO date (YYYY-MM-DD). Stakeholder is the person "
            "this is for. Example: commitment_create(title='Send Sarah Q3 "
            "deck', priority=1, stakeholder='Sarah Chen', deadline='2026-05-01')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short actionable title (e.g., 'Send Sarah Q3 deck').",
                },
                "priority": {
                    "type": "integer",
                    "description": "1 (highest) through 5 (lowest). Default 3.",
                },
                "deadline": {
                    "type": "string",
                    "description": "Optional ISO date YYYY-MM-DD.",
                },
                "stakeholder": {
                    "type": "string",
                    "description": "Who this is for. Free-text name; "
                    "first token is used as a search keyword during verification.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional free-text detail.",
                },
                "source": {
                    "type": "string",
                    "enum": ["chat", "email", "meeting", "manual"],
                    "description": "Where the commitment came from. Default 'manual'.",
                },
                "workstream": {
                    "type": "string",
                    "description": "Optional project / workstream label for grouping.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "commitment_list",
        "description": (
            "List commitments. Defaults to open items sorted by priority then "
            "deadline. Pass status='done' (or 'in_progress', 'blocked', "
            "'cancelled') to see closed/other states."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status. Default 'open'. "
                    "Use 'all' to list everything (open + closed).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return. Default 20.",
                },
            },
        },
    },
    {
        "name": "commitment_update",
        "description": (
            "Update a commitment by id. Only the provided fields change. "
            "Use for flipping status to in_progress/blocked, bumping "
            "priority, setting a deadline, adding description text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "done", "blocked", "cancelled"],
                },
                "priority": {"type": "integer"},
                "deadline": {"type": "string"},
                "description": {"type": "string"},
                "stakeholder": {"type": "string"},
                "workstream": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "commitment_close",
        "description": (
            "Mark a commitment done and log the closure. Use when the user "
            "confirms they finished, or when auto_resolve verification says "
            "VERIFIED DONE and the user agrees. Optional reason captures "
            "what resolved it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "commitment_dismiss",
        "description": (
            "Drop a commitment as cancelled (won't do it, priorities "
            "changed). Logs a 'dismiss' closure. Different from close — "
            "dismiss = intentionally not doing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "commitment_reopen",
        "description": (
            "Reopen a closed or cancelled commitment. Use when the user "
            "says a done item is actually still open."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
]


def _format_commitment(c: dict[str, Any]) -> str:
    stakeholder = f" [{c['stakeholder']}]" if c.get("stakeholder") else ""
    deadline = f" due {c['deadline']}" if c.get("deadline") else ""
    return (
        f"#{c['id']} P{c.get('priority', 3)}: {c['title']}{stakeholder}{deadline} "
        f"— {c.get('status', 'open')}"
    )


def build_commitment_handlers(db: Memory) -> dict[str, Callable[..., str]]:
    """Return the handler dict for AgentLoop. All handlers return strings."""

    def _create(**kwargs: Any) -> str:
        try:
            c = create_commitment(db, **kwargs)
        except Exception as e:
            return f"commitment_create failed: {e}"
        return f"Created {_format_commitment(c)}"

    def _list(status: str = "open", limit: int = 20) -> str:
        if status == "all":
            # Explicit full set — avoids the CRUD layer's "None = open" default.
            status_filter = ["open", "in_progress", "done", "blocked", "cancelled"]
        else:
            status_filter = [status]
        rows = list_commitments(db, status_filter=status_filter, limit=limit)
        if not rows:
            return f"No commitments matching status={status!r}."
        header = f"{len(rows)} commitment(s):"
        body = "\n".join(f"- {_format_commitment(r)}" for r in rows)
        return f"{header}\n{body}"

    def _update(id: int, **fields: Any) -> str:  # noqa: A002 — tool schema uses `id`
        try:
            before = get_commitment(db, id)
            after = update_commitment(db, id, **fields)
        except CommitmentNotFound:
            return f"commitment_update failed: no commitment #{id}"
        except Exception as e:
            return f"commitment_update failed: {e}"
        changes = [
            f"{k}: {before.get(k)} → {after.get(k)}"
            for k in fields
            if before.get(k) != after.get(k)
        ]
        if not changes:
            return f"#{id} unchanged."
        return f"Updated #{id}: " + "; ".join(changes)

    def _close(id: int, reason: str | None = None) -> str:  # noqa: A002
        try:
            c = close_commitment(db, id, reason=reason)
        except CommitmentNotFound:
            return f"commitment_close failed: no commitment #{id}"
        except CommitmentAlreadyClosed:
            return f"commitment_close failed: #{id} already closed"
        except Exception as e:
            return f"commitment_close failed: {e}"
        return f"Closed {_format_commitment(c)}"

    def _dismiss(id: int, reason: str | None = None) -> str:  # noqa: A002
        try:
            c = dismiss_commitment(db, id, reason=reason)
        except CommitmentNotFound:
            return f"commitment_dismiss failed: no commitment #{id}"
        except CommitmentAlreadyClosed:
            return f"commitment_dismiss failed: #{id} already closed"
        except Exception as e:
            return f"commitment_dismiss failed: {e}"
        return f"Dismissed {_format_commitment(c)}"

    def _reopen(id: int) -> str:  # noqa: A002
        try:
            c = reopen_commitment(db, id)
        except CommitmentNotFound:
            return f"commitment_reopen failed: no commitment #{id}"
        except CommitmentNotClosed:
            return f"commitment_reopen failed: #{id} is not closed"
        except Exception as e:
            return f"commitment_reopen failed: {e}"
        return f"Reopened {_format_commitment(c)}"

    return {
        "commitment_create": _create,
        "commitment_list": _list,
        "commitment_update": _update,
        "commitment_close": _close,
        "commitment_dismiss": _dismiss,
        "commitment_reopen": _reopen,
    }
