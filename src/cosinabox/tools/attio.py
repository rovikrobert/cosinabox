"""Attio CRM client."""

from __future__ import annotations

import os
from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[attio] extra is required. Run: pip install 'cosinabox[attio]'"
    ) from e

ATTIO_BASE_URL = "https://api.attio.com/v2"


class AttioError(Exception):
    pass


class AttioClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        key = api_key or os.getenv("ATTIO_API_KEY")
        if not key:
            raise AttioError(
                "ATTIO_API_KEY env var is required. Set it or pass api_key= explicitly."
            )
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **params: Any) -> Any:
        with httpx.Client() as client:
            resp = client.get(f"{ATTIO_BASE_URL}{path}", headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        with httpx.Client() as client:
            resp = client.post(f"{ATTIO_BASE_URL}{path}", headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()

    def _patch(self, path: str, body: dict[str, Any]) -> Any:
        with httpx.Client() as client:
            resp = client.patch(f"{ATTIO_BASE_URL}{path}", headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()

    def _normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        values = record.get("values", {})

        def _first(key: str) -> str:
            items = values.get(key, [])
            if items and isinstance(items, list):
                v = items[0]
                if isinstance(v, dict):
                    return str(v.get("value") or v.get("first_name") or v.get("last_name") or "")
                return str(v)
            return ""

        # Name: try name object or first_name + last_name
        name_items = values.get("name", [])
        if name_items and isinstance(name_items, list):
            nobj = name_items[0] if isinstance(name_items[0], dict) else {}
            first = nobj.get("first_name") or nobj.get("value", "")
            last = nobj.get("last_name", "")
            name = f"{first} {last}".strip() if (first or last) else ""
        else:
            name = ""

        title = _first("job_title")
        company_items = values.get("primary_company", [])
        company = ""
        if company_items and isinstance(company_items, list):
            cobj = company_items[0] if isinstance(company_items[0], dict) else {}
            company = str(cobj.get("target_record", {}).get("name", "") or cobj.get("value", ""))

        role = f"{title} at {company}".strip() if title and company else title or company

        rec_id = record.get("id", {})
        resolved_id = rec_id.get("record_id") if isinstance(rec_id, dict) else rec_id or ""
        return {
            "id": resolved_id,
            "name": name,
            "role": role,
        }

    def list_people(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._post("/objects/people/records/query", {"limit": limit})
        result: list[dict[str, Any]] = [self._normalize(r) for r in data.get("data", [])]
        return result

    def get_person(self, name: str) -> dict[str, Any] | None:
        data = self._post(
            "/objects/people/records/query",
            {"filter": {"name": {"$str_contains": name}}, "limit": 1},
        )
        records = data.get("data", [])
        if not records:
            return None
        result: dict[str, Any] = self._normalize(records[0])
        return result

    def search_people(self, query: str) -> list[dict[str, Any]]:
        data = self._post(
            "/objects/people/records/query",
            {"filter": {"name": {"$str_contains": query}}},
        )
        result: list[dict[str, Any]] = [self._normalize(r) for r in data.get("data", [])]
        return result

    def update_person(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        data = self._patch(f"/objects/people/records/{record_id}", {"values": fields})
        result: dict[str, Any] = self._normalize(data.get("data", data))
        return result

    def create_person(self, fields: dict[str, Any]) -> dict[str, Any]:
        data = self._post("/objects/people/records", {"values": fields})
        result: dict[str, Any] = self._normalize(data.get("data", data))
        return result
