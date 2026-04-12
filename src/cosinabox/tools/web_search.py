"""Serper.dev web search tool (optional dep: cosinabox[search])."""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[search] extra is required. Run: pip install 'cosinabox[search]'"
    ) from e

SERPER_URL = "https://google.serper.dev/search"


class WebSearchTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, num: int = 10) -> list[dict[str, Any]]:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                SERPER_URL,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num},
            )
        return resp.json().get("organic", []) or []
