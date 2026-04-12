from __future__ import annotations

from unittest.mock import MagicMock, patch

from cosinabox.tools.fireflies import FirefliesTool


def test_list_recent_parses_graphql_response() -> None:
    with patch("cosinabox.tools.fireflies.httpx.Client") as MockClient:
        client = MagicMock()
        MockClient.return_value.__enter__.return_value = client
        client.post.return_value.json.return_value = {
            "data": {
                "transcripts": [
                    {"id": "t1", "title": "Standup", "date": "2026-04-12T10:00:00Z"}
                ]
            }
        }
        tool = FirefliesTool(api_key="fake")
        meetings = tool.list_recent_meetings(hours=24)
        assert len(meetings) == 1
        assert meetings[0]["id"] == "t1"
