"""DM handler, pending-tool TTL, and approval logic."""

from __future__ import annotations

_APPROVAL_PHRASES: frozenset[str] = frozenset(
    {
        "yes",
        "yep",
        "yeah",
        "y",
        "go ahead",
        "approved",
        "do it",
        "send it",
        "ok",
        "okay",
        "k",
        "sure",
        "confirm",
        "approve",
        "absolutely",
        "definitely",
    }
)


def is_approval(text: str, *, has_pending_tool: bool) -> bool:
    """Return True iff ``text`` is an approval for a pending tool call.

    Tightened semantics (Plan 4 polish, item 7):
      1. The text must EXACTLY match a phrase in ``_APPROVAL_PHRASES``
         after whitespace-strip + lowercase. The previous first-word
         fallback accepted "yes but actually no" as approval (bug).
      2. There must be a pending tool waiting in the session. Bare "ok"
         or "k" mid-conversation (with no tool waiting) is NOT an
         approval — ``has_pending_tool`` is the caller's guard.

    Both conditions must hold, because either alone leaves a footgun:
      - Without (1), "yes but let's hold off" slips through.
      - Without (2), "k" as a casual ack could silently re-approve a
        stale tool.
    """
    if not has_pending_tool:
        return False
    normalized = " ".join(text.strip().lower().split())
    return normalized in _APPROVAL_PHRASES
