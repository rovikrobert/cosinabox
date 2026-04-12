"""`cosinabox[attio]` — Attio CRM client."""

from __future__ import annotations

import os
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment,unused-ignore]

_BASE = "https://api.attio.com/v2"


class AttioClient:
    """Synchronous Attio v2 API client."""

    def __init__(self) -> None:
        if httpx is None:
            raise ImportError(
                "cosinabox[attio] extra is required. Run: pip install 'cosinabox[attio]'"
            )
        api_key = os.environ.get("ATTIO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ATTIO_API_KEY environment variable is required when attio integration is enabled."
            )
        self._http = httpx.Client(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )

    def list_people(self, limit: int = 50) -> list[dict[str, Any]]:
        """List people from Attio."""
        resp = self._http.post(
            "/objects/people/records/query",
            json={"limit": limit},
        )
        resp.raise_for_status()
        return [self._normalize(r) for r in resp.json().get("data", [])]

    def get_person(self, name: str) -> dict[str, Any] | None:
        """Find a person by name. Returns None if not found."""
        resp = self._http.post(
            "/objects/people/records/query",
            json={
                "filter": {
                    "name": {"$contains": name},
                },
                "limit": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return self._normalize(data[0])

    def search_people(self, query: str) -> list[dict[str, Any]]:
        """Search people by query string."""
        return [
            p for p in self.list_people(limit=100) if query.lower() in p.get("name", "").lower()
        ]

    def update_person(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update a person record."""
        resp = self._http.patch(
            f"/objects/people/records/{record_id}",
            json={"data": {"values": fields}},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json().get("data", {})
        return result

    def create_person(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Create a new person record."""
        resp = self._http.post(
            "/objects/people/records",
            json={"data": {"values": fields}},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json().get("data", {})
        return result

    @staticmethod
    def _normalize(record: dict[str, Any]) -> dict[str, Any]:
        """Normalize an Attio record to a flat dict."""
        values = record.get("values", {})
        name_parts = values.get("name", [{}])
        first = name_parts[0].get("first_name", "") if name_parts else ""
        last = name_parts[0].get("last_name", "") if name_parts else ""
        title_parts = values.get("job_title", [{}])
        title = title_parts[0].get("value", "") if title_parts else ""
        company_parts = values.get("company", [{}])
        company = company_parts[0].get("value", "") if company_parts else ""
        return {
            "id": record.get("id", {}).get("object_id", ""),
            "name": f"{first} {last}".strip(),
            "role": f"{title} at {company}".strip() if title and company else (title or company),
            "title": title,
            "company": company,
        }
