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
    def __init__(
        self,
        *,
        service: Resource | None = None,
        services: list[Resource] | None = None,
    ) -> None:
        if services:
            self._services = services
        elif service:
            self._services = [service]
        else:
            from cosinabox.tools.google.auth import build_all_credentials

            creds_list = build_all_credentials()
            self._services = [build("gmail", "v1", credentials=c) for c in creds_list]

    def list_recent(self, *, hours: int = 24, max_results: int = 25) -> list[GmailMessage]:
        after = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y/%m/%d")
        query = f"after:{after}"
        all_msgs: list[GmailMessage] = []
        seen_ids: set[str] = set()
        for svc in self._services:
            resp = (
                svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            )
            for ref in resp.get("messages", []):
                if ref["id"] in seen_ids:
                    continue
                seen_ids.add(ref["id"])
                full = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=ref["id"], format="metadata")
                    .execute()
                )
                payload = full.get("payload", {})
                all_msgs.append(
                    GmailMessage(
                        id=full["id"],
                        sender=_header(payload, "From"),
                        subject=_header(payload, "Subject"),
                        snippet=full.get("snippet", ""),
                        date=_header(payload, "Date"),
                    )
                )
        return all_msgs[:max_results]

    def search(self, query: str, *, max_results: int = 25) -> list[GmailMessage]:
        all_msgs: list[GmailMessage] = []
        seen_ids: set[str] = set()
        for svc in self._services:
            resp = (
                svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            )
            for ref in resp.get("messages", []):
                if ref["id"] in seen_ids:
                    continue
                seen_ids.add(ref["id"])
                full = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=ref["id"], format="metadata")
                    .execute()
                )
                payload = full.get("payload", {})
                all_msgs.append(
                    GmailMessage(
                        id=full["id"],
                        sender=_header(payload, "From"),
                        subject=_header(payload, "Subject"),
                        snippet=full.get("snippet", ""),
                        date=_header(payload, "Date"),
                    )
                )
        return all_msgs[:max_results]
