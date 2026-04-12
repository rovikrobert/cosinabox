"""Conversation summarization (>25 messages by default).

Layer 1: long contexts degrade quality and burn money.
"""

from __future__ import annotations

from typing import Any

SUMMARIZE_MODEL = "claude-sonnet-4-6"


def maybe_summarize(
    messages: list[dict[str, Any]],
    *,
    client: Any,
    threshold: int = 25,
    keep_recent: int = 10,
) -> list[dict[str, Any]]:
    if len(messages) < threshold:
        return messages
    to_summarize = messages[: len(messages) - keep_recent]
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in to_summarize if isinstance(m.get("content"), str)
    )
    response = client.messages.create(
        model=SUMMARIZE_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize the following conversation in <=200 words. "
                    "Preserve names, decisions, and open commitments.\n\n" + transcript
                ),
            }
        ],
    )
    summary_text = "\n".join(b.text for b in response.content if b.type == "text")
    summary_msg = {
        "role": "assistant",
        "content": f"[Earlier conversation summary]\n{summary_text}",
    }
    return [summary_msg, *messages[-keep_recent:]]
