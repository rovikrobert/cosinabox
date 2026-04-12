"""Conversation summarization — compact old messages via Sonnet.

When a session's message count exceeds CONVERSATION_SUMMARIZE_THRESHOLD,
the oldest messages are summarized into a single text block, stored as
a summary, and the originals are deleted. The summary is injected into
the system prompt by AgentLoop.run().
"""

from __future__ import annotations

import logging
from typing import Any

from cosinabox import defaults
from cosinabox.agent.routing import SONNET_MODEL_ID

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
Summarize the following conversation messages into a concise context block.

MUST PRESERVE:
- Key decisions made and their rationale
- Names, organizations, and relationships mentioned
- Specific identifiers: email addresses, dates, amounts, URLs — copy exactly
- Topics discussed and conclusions reached

CONDENSE OR OMIT:
- Greetings, pleasantries, acknowledgments
- Tool execution details ("I searched Gmail and found...")
- Repeated information
- Verbose raw data from tools

Output only the summary, no preamble. Use bullet points for clarity.
Keep it under 500 words.

MESSAGES:
"""


def maybe_summarize(
    *,
    memory: Any,
    session_id: str,
    anthropic_client: Any,
) -> None:
    """Summarize old messages if the session exceeds the threshold.

    This is called at the start of each AgentLoop.run() when memory
    is available. It's synchronous (matches the loop's sync design).
    """
    count = memory.message_count(session_id=session_id)
    if count <= defaults.CONVERSATION_SUMMARIZE_THRESHOLD:
        return

    to_summarize = count - defaults.CONVERSATION_SUMMARIZE_KEEP_RECENT
    if to_summarize < 5:
        return

    logger.info(
        "Summarizing %d messages for session %s (%d total)",
        to_summarize,
        session_id,
        count,
    )

    old_messages = memory.oldest_messages(
        session_id=session_id, count=to_summarize,
    )

    # Build the prompt from old messages
    lines = []
    for msg in old_messages:
        role = msg["role"].upper()
        content = msg["content"]
        # Truncate very long messages to keep summarization prompt manageable
        if len(content) > 2000:
            content = content[:2000] + "... (truncated)"
        lines.append(f"[{role}]: {content}")

    messages_text = "\n\n".join(lines)
    prompt = _SUMMARIZE_PROMPT + messages_text

    try:
        response = anthropic_client.messages.create(
            model=SONNET_MODEL_ID,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text = "\n".join(
            b.text for b in response.content if b.type == "text"
        )
    except Exception:
        logger.warning("Summarization API call failed — skipping", exc_info=True)
        return

    if not summary_text.strip():
        logger.warning("Summarization returned empty — skipping")
        return

    # Store summary and delete old messages
    memory.store_summary(
        session_id=session_id,
        summary=summary_text,
        messages_summarized=len(old_messages),
    )

    ids_to_delete = [msg["id"] for msg in old_messages]
    deleted = memory.delete_messages_by_ids(ids_to_delete)
    logger.info(
        "Summarized %d messages into %d chars, deleted %d rows",
        len(old_messages),
        len(summary_text),
        deleted,
    )
