"""Tavily search tool (optional dep: cosinabox[research]).

Used by the research digest's collector rather than by the chat tool loop.
Tavily is the backend here specifically because it exposes a news topic and a
date window; a general web search over the same queries returns evergreen
product pages, which the synthesizer's recency gate then discards — that
failure starved several tracked entities of signal for months in the legacy
implementation.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ImportError as e:  # pragma: no cover - exercised by the extras guard
    raise ImportError(
        "cosinabox[research] extra is required. Run: pip install 'cosinabox[research]'"
    ) from e

TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = 20.0


class TavilyTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def search(
        self,
        query: str,
        *,
        country: str,
        topic: str,
        time_range: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "query": query,
            "country": country,
            "topic": topic,
            "max_results": max_results,
        }
        # Only meaningful alongside topic="news"; sending it on a general
        # search is silently ignored upstream, so keep the payload honest.
        if time_range:
            body["time_range"] = time_range

        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                TAVILY_URL,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Tavily search failed (HTTP {resp.status_code})")

        out: list[dict[str, Any]] = []
        for item in resp.json().get("results") or []:
            url = item.get("url") or ""
            if not url:
                continue
            out.append(
                {
                    "title": item.get("title") or "",
                    "url": url,
                    "snippet": item.get("content") or "",
                    "published": item.get("published_date") or "",
                    "source": urlparse(url).netloc,
                }
            )
        return out
