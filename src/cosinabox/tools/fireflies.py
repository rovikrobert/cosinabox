"""Fireflies meeting transcripts (optional dep: cosinabox[fireflies])."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[fireflies] extra is required. "
        "Run: pip install 'cosinabox[fireflies]'"
    ) from e

FIREFLIES_GRAPHQL_URL = "https://api.fireflies.ai/graphql"


class FirefliesTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def list_recent_meetings(self, *, hours: int = 24) -> list[dict[str, Any]]:
        after = datetime.now(UTC) - timedelta(hours=hours)
        query = """
        query Recent($after: DateTime!) {
            transcripts(fromDate: $after) { id title date }
        }
        """
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                FIREFLIES_GRAPHQL_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": {"after": after.isoformat()}},
            )
        return resp.json().get("data", {}).get("transcripts", []) or []

    def get_transcript(self, meeting_id: str) -> dict[str, Any]:
        query = """
        query Transcript($id: String!) {
            transcript(id: $id) { id title sentences { text speaker_name } }
        }
        """
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                FIREFLIES_GRAPHQL_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": {"id": meeting_id}},
            )
        return resp.json().get("data", {}).get("transcript", {}) or {}
