"""Model routing and per-channel tool subsets.

When ADVISOR_ENABLED, strategic prompts route to Sonnet + Opus advisor
instead of direct Opus. Includes conversation escalation — if the last
4 messages are all strategic, escalate even if the current message isn't.
"""

from __future__ import annotations

import re
from typing import Any

from cosinabox import defaults

OPUS_SIGNALS = [
    r"\b(strategy|trade-?off|position(?:ing)?|pre.?mortem|blind spot)\b",
    r"\b(investor update|board prep|strategy doc|proposal|narrative)\b",
    r"\b(stress.?test|second.?order|implications|what am i missing)\b",
    r"\b(career|reputation|leverage)\b",
    r"\b(what if.*then|push back on|challenge (this|my|the))\b",
]

MODERATE_SIGNALS = [
    r"\b(compare|analyze|evaluat(e|ion)|pros and cons|options for)\b",
    r"\b(trade.?offs?|weigh|assess|critique|review (this|my|the))\b",
    r"\b(how should (i|we)|what.?s the best (way|approach))\b",
    r"\b(prioriti[sz]e|rank|recommend)\b",
]

SONNET_OVERRIDES = [
    r"^(what('s| is) on my calendar|check my calendar|schedule)\b",
    r"^(find|search|look up)\s+(email|message)",
    r"^(what time|when is|remind me)",
    r"^(summarize|summary|tldr)\b",
]

GROUP_SAFE_TOOLS = frozenset({"calendar", "web_search"})

SONNET_MODEL_ID = defaults.SONNET_MODEL_ID
OPUS_MODEL_ID = defaults.OPUS_MODEL_ID

THINKING_ADAPTIVE = {"type": "adaptive"}


def _conversation_is_strategic(context: list[dict[str, Any]]) -> bool:
    """Check if the recent conversation is strategically dense.

    If 3+ of the last 4 messages match OPUS_SIGNALS, escalate —
    even if the current message alone wouldn't trigger it.
    """
    recent = context[-4:] if len(context) >= 4 else context
    strategic_count = 0
    for msg in recent:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        for pattern in OPUS_SIGNALS:
            if re.search(pattern, content, re.IGNORECASE):
                strategic_count += 1
                break
    return strategic_count >= 3


class Router:
    def __init__(
        self,
        *,
        available_tools: set[str] | None = None,
    ) -> None:
        self.available_tools = available_tools or set()

    def choose_model(
        self,
        prompt: str,
        conversation_context: list[dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, str] | None, bool]:
        """Route to model. Returns (model, thinking_config, use_advisor).

        When advisor is enabled, strategic prompts use Sonnet + advisor
        instead of Opus directly.
        """
        msg_lower = prompt.lower().strip()

        # Sonnet overrides — always Sonnet, no advisor
        for pattern in SONNET_OVERRIDES:
            if re.search(pattern, msg_lower):
                return SONNET_MODEL_ID, None, False

        # Opus signals — advisor if enabled, else Opus + thinking
        for pattern in OPUS_SIGNALS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                if defaults.ADVISOR_ENABLED:
                    return SONNET_MODEL_ID, None, True
                return OPUS_MODEL_ID, THINKING_ADAPTIVE, False

        # Moderate signals — advisor if enabled, else Sonnet + thinking
        for pattern in MODERATE_SIGNALS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                if defaults.ADVISOR_ENABLED:
                    return SONNET_MODEL_ID, None, True
                return SONNET_MODEL_ID, THINKING_ADAPTIVE, False

        # Conversation escalation — if recent context is strategically dense
        if conversation_context and _conversation_is_strategic(
            conversation_context
        ):
            if defaults.ADVISOR_ENABLED:
                return SONNET_MODEL_ID, None, True
            return OPUS_MODEL_ID, THINKING_ADAPTIVE, False

        # Default: Sonnet, no thinking, no advisor
        return SONNET_MODEL_ID, None, False

    def tools_for_channel(self, channel: str) -> set[str]:
        if channel == "group":
            return self.available_tools & GROUP_SAFE_TOOLS
        return set(self.available_tools)
