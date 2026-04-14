"""Policy engine — approval gates for tool execution.

Evaluates whether a tool call should be allowed, denied, or require
user approval before execution. Rules are pattern-matched against tool
names with optional field conditions.

Default rules:
- Read tools (gmail_search, calendar_list_events, etc.) → ALLOW
- Draft creation (gmail_compose) → ALLOW (drafts are safe)
- Send/delete operations → REQUIRE_APPROVAL
- Unknown tools → REQUIRE_APPROVAL (safe default)

Users can override defaults via policy_rules in integrations.yaml.
"""

from __future__ import annotations

import fnmatch
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyResult:
    decision: Decision
    description: str
    tool_name: str


# ---------------------------------------------------------------------------
# Temporary approval tokens (one-shot, in-memory, TTL-based)
# ---------------------------------------------------------------------------

_APPROVAL_TTL_S = 120  # 2 minutes

# (session_id, tool_name) → grant timestamp
_pending_approvals: dict[tuple[str, str], float] = {}


def _sweep_expired_approvals() -> None:
    """Evict approval tokens past their TTL. Prevents unbounded dict growth
    from abandoned sessions that never approve/reject."""
    now = time.time()
    expired = [k for k, ts in _pending_approvals.items() if now - ts > _APPROVAL_TTL_S]
    for k in expired:
        del _pending_approvals[k]


def grant_temporary_approval(session_id: str, tool_name: str) -> None:
    """Grant a one-shot approval for a specific tool in a session."""
    _sweep_expired_approvals()
    _pending_approvals[(session_id, tool_name)] = time.time()
    logger.info("Granted temporary approval: %s in %s", tool_name, session_id)


def _check_temporary_approval(session_id: str, tool_name: str) -> bool:
    """Check and consume a temporary approval token."""
    _sweep_expired_approvals()
    key = (session_id, tool_name)
    granted_at = _pending_approvals.get(key)
    if granted_at is None:
        return False
    # Consume the token
    del _pending_approvals[key]
    if time.time() - granted_at > _APPROVAL_TTL_S:
        return False  # expired
    return True


def clear_approvals() -> None:
    """Clear all pending approvals (for testing)."""
    _pending_approvals.clear()


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------


@dataclass
class PolicyRule:
    tool_pattern: str  # fnmatch pattern, e.g. "gmail_*"
    action: Decision
    condition_field: str = ""  # optional: field in tool_input to check
    condition_op: str = ""  # contains, not_contains, eq
    condition_value: str = ""  # operand
    priority: int = 100  # lower = higher priority
    description: str = ""


# Rules are evaluated in priority order (lower first). First match wins.
DEFAULT_RULES: list[PolicyRule] = [
    # Read-only tools — always safe
    PolicyRule(
        "gmail_search", Decision.ALLOW, priority=200, description="Email search is read-only"
    ),
    PolicyRule(
        "gmail_list_recent", Decision.ALLOW, priority=200, description="Email listing is read-only"
    ),
    PolicyRule(
        "calendar_list_events", Decision.ALLOW, priority=200, description="Calendar read is safe"
    ),
    PolicyRule(
        "calendar_find_conflicts",
        Decision.ALLOW,
        priority=200,
        description="Conflict check is read-only",
    ),
    PolicyRule(
        "calendar_find_free_time",
        Decision.ALLOW,
        priority=200,
        description="Free time check is read-only",
    ),
    PolicyRule("crm_*", Decision.ALLOW, priority=200, description="CRM read is safe"),
    PolicyRule(
        "fireflies_*", Decision.ALLOW, priority=200, description="Transcript access is read-only"
    ),
    PolicyRule("web_search", Decision.ALLOW, priority=200, description="Web search is read-only"),
    PolicyRule(
        "rela_query",
        Decision.ALLOW,
        priority=200,
        description="Sub-agent query is read-only",
    ),
    # Drafts are safe (user reviews before sending)
    PolicyRule(
        "gmail_compose",
        Decision.ALLOW,
        priority=100,
        description="Drafts don't send — user reviews",
    ),
    PolicyRule(
        "gmail_draft_reply", Decision.ALLOW, priority=100, description="Draft replies don't send"
    ),
    # Write operations — require approval
    PolicyRule(
        "gmail_send",
        Decision.REQUIRE_APPROVAL,
        priority=60,
        description="Sending email requires approval",
    ),
    PolicyRule(
        "calendar_create_event",
        Decision.REQUIRE_APPROVAL,
        priority=60,
        description="Creating events requires approval",
    ),
    # Catch-all — unknown tools require approval (safe default)
    PolicyRule(
        "*", Decision.REQUIRE_APPROVAL, priority=999, description="Unknown tool requires approval"
    ),
]


def _load_rules(
    custom_rules: list[dict[str, Any]] | None = None,
) -> list[PolicyRule]:
    """Merge custom rules with defaults. Custom rules take priority."""
    rules = list(DEFAULT_RULES)

    if custom_rules:
        for r in custom_rules:
            rules.append(
                PolicyRule(
                    tool_pattern=r["tool_pattern"],
                    action=Decision(r["action"]),
                    condition_field=r.get("condition_field", ""),
                    condition_op=r.get("condition_op", ""),
                    condition_value=r.get("condition_value", ""),
                    priority=r.get("priority", 50),
                    description=r.get("description", ""),
                )
            )

    rules.sort(key=lambda r: r.priority)
    return rules


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _check_condition(rule: PolicyRule, tool_input: dict[str, Any]) -> bool:
    """Check if a rule's condition matches the tool input."""
    if not rule.condition_field:
        return True  # no condition = unconditional match

    value = tool_input.get(rule.condition_field, "")
    if isinstance(value, list):
        value = ",".join(str(v) for v in value)
    value = str(value).lower()
    target = rule.condition_value.lower()

    if rule.condition_op == "contains":
        return target in value
    if rule.condition_op == "not_contains":
        return target not in value
    if rule.condition_op == "eq":
        return value == target
    if rule.condition_op == "neq":
        return value != target

    return True  # unknown op = match


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cached_rules: list[PolicyRule] | None = None


def evaluate(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    session_id: str = "",
    custom_rules: list[dict[str, Any]] | None = None,
) -> PolicyResult:
    """Evaluate policy for a tool call.

    Returns a PolicyResult with the decision (ALLOW, DENY, REQUIRE_APPROVAL).
    """
    global _cached_rules

    # Check temporary approval first (one-shot bypass)
    if session_id and _check_temporary_approval(session_id, tool_name):
        return PolicyResult(
            decision=Decision.ALLOW,
            description="Temporary approval granted by user",
            tool_name=tool_name,
        )

    # Load and cache rules
    if _cached_rules is None or custom_rules is not None:
        _cached_rules = _load_rules(custom_rules)

    # Evaluate rules in priority order
    for rule in _cached_rules:
        if not fnmatch.fnmatch(tool_name, rule.tool_pattern):
            continue
        if not _check_condition(rule, tool_input):
            continue
        # First matching rule wins
        return PolicyResult(
            decision=rule.action,
            description=rule.description,
            tool_name=tool_name,
        )

    # No rules matched — safe default
    return PolicyResult(
        decision=Decision.REQUIRE_APPROVAL,
        description="No matching policy rule — approval required",
        tool_name=tool_name,
    )


def invalidate_cache() -> None:
    """Clear cached rules (call after config changes)."""
    global _cached_rules
    _cached_rules = None
