from __future__ import annotations

from unittest.mock import MagicMock, patch

from cosinabox.tools.web_search import WebSearchTool


def test_search_returns_results() -> None:
    with patch("cosinabox.tools.web_search.httpx.Client") as MockClient:
        client = MagicMock()
        MockClient.return_value.__enter__.return_value = client
        client.post.return_value.json.return_value = {
            "organic": [
                {"title": "T1", "link": "https://x.com", "snippet": "S1"},
                {"title": "T2", "link": "https://y.com", "snippet": "S2"},
            ]
        }
        tool = WebSearchTool(api_key="fake")
        results = tool.search("test query")
        assert len(results) == 2
        assert results[0]["title"] == "T1"
