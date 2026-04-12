"""Model routing and per-channel tool subsets.

Layer 1 defaults:
- Sonnet by default; Opus on strategic-keyword prompts
- Group chats restricted to calendar + web_search (group mode exposes
  too much surface)
"""

from __future__ import annotations

DEFAULT_STRATEGIC_KEYWORDS = frozenset(
    {
        "strategy",
        "strategic",
        "hiring",
        "fundraise",
        "fundraising",
        "board",
        "investors",
        "vision",
        "roadmap",
        "OKR",
        "OKRs",
    }
)

GROUP_SAFE_TOOLS = frozenset({"calendar", "web_search"})

SONNET_MODEL_ID = "claude-sonnet-4-6"
OPUS_MODEL_ID = "claude-opus-4-6"


class Router:
    def __init__(
        self,
        *,
        available_tools: set[str] | None = None,
        strategic_keywords: frozenset[str] = DEFAULT_STRATEGIC_KEYWORDS,
    ) -> None:
        self.available_tools = available_tools or set()
        self.strategic_keywords = strategic_keywords

    def choose_model(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(kw.lower() in lowered for kw in self.strategic_keywords):
            return OPUS_MODEL_ID
        return SONNET_MODEL_ID

    def tools_for_channel(self, channel: str) -> set[str]:
        if channel == "group":
            return self.available_tools & GROUP_SAFE_TOOLS
        return set(self.available_tools)
