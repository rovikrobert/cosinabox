"""Gmail tool — read-only listing and search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_credentials


@dataclass
class GmailMessage:
    id: str
    sender: str
    subject: str
    snippet: str
    date: str


def _header(payload: dict[str, Any], name: str) -> str:
    for h in payload.get("headers", []):
        if h["name"].lower() == name.lower():
            return str(h["value"])
    return ""


class GmailTool:
    def __init__(self, *, service: Resource | None = None) -> None:
        if service is None:
            service = build("gmail", "v1", credentials=build_credentials())
        self.service = service

    def list_recent(
        self, *, hours: int = 24, max_results: int = 25
    ) -> list[GmailMessage]:
        after = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y/%m/%d")
        query = f"after:{after}"
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        out: list[GmailMessage] = []
        for ref in resp.get("messages", []):
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata")
                .execute()
            )
            payload = full.get("payload", {})
            out.append(
                GmailMessage(
                    id=full["id"],
                    sender=_header(payload, "From"),
                    subject=_header(payload, "Subject"),
                    snippet=full.get("snippet", ""),
                    date=_header(payload, "Date"),
                )
            )
        return out

    def search(self, query: str, *, max_results: int = 25) -> list[GmailMessage]:
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        out: list[GmailMessage] = []
        for ref in resp.get("messages", []):
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata")
                .execute()
            )
            payload = full.get("payload", {})
            out.append(
                GmailMessage(
                    id=full["id"],
                    sender=_header(payload, "From"),
                    subject=_header(payload, "Subject"),
                    snippet=full.get("snippet", ""),
                    date=_header(payload, "Date"),
                )
            )
        return out
