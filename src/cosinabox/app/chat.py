"""DM handler, pending-tool TTL, and approval logic."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("cosinabox")


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


_PENDING_TOOL_TTL_S = 300  # 5 minutes


def build_dm_handler(loop: Any, chat_id: str) -> Any:
    """Build the Telegram DM handler (async) with pending-tool TTL tracking.

    Returns an async function suitable for ``MessageHandler``.
    """
    from cosinabox.agent.loop import AgentLoop

    assert isinstance(loop, AgentLoop)

    # Track tools pending approval per session (may be multiple).
    # Value is (list_of_tool_names, timestamp) so we can evict stale
    # entries from abandoned sessions.
    _pending_tools: dict[str, tuple[list[str], float]] = {}
    # The DM handler runs on the PTB async loop thread, while the sweep
    # can be called by the same handler mid-request; scheduling outreach
    # and agent loop errors may interleave. Protect all accesses.
    # NOTE: threading.Lock deliberately, NOT asyncio.Lock — scheduling
    # outreach runs on sync worker threads.
    _pending_tools_lock = threading.Lock()

    def _sweep_pending_tools() -> None:
        now = time.time()
        with _pending_tools_lock:
            expired = [
                sid for sid, (_, ts) in _pending_tools.items() if now - ts > _PENDING_TOOL_TTL_S
            ]
            for sid in expired:
                del _pending_tools[sid]

    async def handle_message(update: Any, _ctx: Any) -> None:
        if update.message is None or update.message.text is None:
            return
        if update.effective_chat is None:
            return
        if str(update.effective_chat.id) != chat_id:
            return

        user_text = update.message.text
        session = f"dm-{update.effective_chat.id}"
        logger.info("DM: %s", user_text[:80])

        _sweep_pending_tools()

        # Check if this message is an approval for pending tools. Both
        # conditions (exact-match normalised phrase AND session has a
        # pending tool) are enforced by ``is_approval``.
        tool_names_to_grant: list[str] = []
        with _pending_tools_lock:
            has_pending = session in _pending_tools
            if has_pending and is_approval(user_text, has_pending_tool=True):
                tool_names, _ts = _pending_tools.pop(session)
                tool_names_to_grant = tool_names
        if tool_names_to_grant:
            from cosinabox.agent.policy import grant_temporary_approval

            for tool_name in tool_names_to_grant:
                grant_temporary_approval(session, tool_name)
                logger.info("User approved %s in %s", tool_name, session)

        blocked: list[str] = []
        try:
            result = loop.run(prompt=user_text, session_id=session)
            reply = result.final_text or "(no response)"
            blocked = [tc.name for tc in result.tool_calls if "APPROVAL REQUIRED" in tc.result]
        except Exception:
            logger.exception("Agent loop failed")
            reply = "(error processing message)"
        if blocked:
            with _pending_tools_lock:
                _pending_tools[session] = (blocked, time.time())

        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i : i + 4000])

    return handle_message
