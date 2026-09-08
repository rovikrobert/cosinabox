from __future__ import annotations

from typing import Any

import pytest

from cosinabox.tools.tavily import TavilyTool

RAW = {
    "results": [
        {
            "title": "Org Alpha ships a thing",
            "url": "https://example.com/a",
            "content": "Body text.",
            "published_date": "2026-08-18",
        },
        {"title": "No url", "content": "x"},
    ]
}


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def test_search_normalises_results_and_drops_urlless(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    items = TavilyTool(api_key="k").search(
        "Org Alpha", country="us", topic="news", time_range="week", max_results=4
    )

    assert items == [
        {
            "title": "Org Alpha ships a thing",
            "url": "https://example.com/a",
            "snippet": "Body text.",
            "published": "2026-08-18",
            "source": "example.com",
        }
    ]


def test_news_topic_sends_the_time_window(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    TavilyTool(api_key="k").search(
        "q", country="us", topic="news", time_range="week", max_results=3
    )

    body = fake.calls[0]["json"]
    assert body["topic"] == "news"
    assert body["time_range"] == "week"
    assert body["max_results"] == 3
    assert body["country"] == "us"


def test_general_topic_omits_time_range(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    TavilyTool(api_key="k").search(
        "q", country="us", topic="general", time_range=None, max_results=3
    )

    assert "time_range" not in fake.calls[0]["json"]


def test_non_200_raises(monkeypatch):
    fake = _FakeClient(_FakeResponse({"error": "nope"}, status=401))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    with pytest.raises(RuntimeError, match="Tavily search failed"):
        TavilyTool(api_key="k").search(
            "q", country="us", topic="news", time_range="week", max_results=3
        )
