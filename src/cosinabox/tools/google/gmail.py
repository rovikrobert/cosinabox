"""Gmail tool — read-only listing and search."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from typing import Any

try:
    from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_all_credentials

logger = logging.getLogger(__name__)


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


def _fetch_messages(service: Resource, q: str, max_results: int) -> list[GmailMessage]:
    # Gmail search index lags up to 1 hour on sent mail.
    # Use labelIds=["SENT"] for reliable sent mail queries.
    if re.search(r"\bin:sent\b", q):
        stripped_q = re.sub(r"\bin:sent\b", "", q).strip()
        resp = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["SENT"], q=stripped_q or None, maxResults=max_results)
            .execute()
        )
    else:
        resp = service.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    out: list[GmailMessage] = []
    for ref in resp.get("messages", []):
        full = (
            service.users().messages().get(userId="me", id=ref["id"], format="metadata").execute()
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


class GmailTool:
    def __init__(
        self,
        *,
        service: Resource | None = None,
        services: list[Resource] | None = None,
    ) -> None:
        if services is not None:
            self._services = services
        elif service is not None:
            self._services = [service]
        else:
            self._services = [
                build("gmail", "v1", credentials=cred) for cred in build_all_credentials()
            ]
        # Backwards compat: expose first service as .service
        self.service = self._services[0]

    def list_recent(self, *, hours: int = 24, max_results: int = 25) -> list[GmailMessage]:
        after = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y/%m/%d")
        query = f"after:{after}"
        seen: set[str] = set()
        out: list[GmailMessage] = []
        for svc in self._services:
            for msg in _fetch_messages(svc, query, max_results):
                if msg.id not in seen:
                    seen.add(msg.id)
                    out.append(msg)
        return out

    def get_recipients(self, message_id: str) -> list[str]:
        """Fetch the To + Cc email addresses for a single message.

        Returns a deduplicated list of lowercased email addresses parsed from
        the message's To and Cc headers. Uses format=metadata with
        metadataHeaders=['To','Cc'] to minimise the API payload.

        Returns ``[]`` on any API error so callers (e.g. CrmEmailSyncJob) stay
        robust when a single message fails.
        """
        # Try each configured account until one returns the message. This mirrors
        # _fetch_messages which dedupes across accounts.
        for svc in self._services:
            try:
                full = (
                    svc.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["To", "Cc"],
                    )
                    .execute()
                )
            except Exception:
                logger.debug("get_recipients failed for %s", message_id, exc_info=True)
                continue
            payload = full.get("payload", {}) if isinstance(full, dict) else {}
            to_raw = _header(payload, "To")
            cc_raw = _header(payload, "Cc")
            # email.utils.getaddresses is the canonical RFC 5322 parser.
            pairs = getaddresses([to_raw, cc_raw])
            seen: set[str] = set()
            out: list[str] = []
            for _, addr in pairs:
                addr = addr.strip().lower()
                if addr and addr not in seen:
                    seen.add(addr)
                    out.append(addr)
            return out
        return []

    def search(self, query: str, *, max_results: int = 25) -> list[GmailMessage]:
        seen: set[str] = set()
        out: list[GmailMessage] = []
        for svc in self._services:
            for msg in _fetch_messages(svc, query, max_results):
                if msg.id not in seen:
                    seen.add(msg.id)
                    out.append(msg)
        return out

    def compose_draft(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        account_index: int = 0,
    ) -> dict[str, str]:
        """Create an email draft. Does NOT send — user reviews first.

        Returns dict with draft_id and message.
        """
        import base64
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc = self._services[min(account_index, len(self._services) - 1)]
        draft = (
            svc.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return {
            "draft_id": draft["id"],
            "message": f"Draft created (ID: {draft['id']}). Review in Gmail before sending.",
        }

    def send_draft(self, *, draft_id: str, account_index: int = 0) -> dict[str, str]:
        """Send an existing draft by ID. Requires user approval."""
        svc = self._services[min(account_index, len(self._services) - 1)]
        try:
            result = (
                svc.users()
                .drafts()
                .send(userId="me", body={"id": draft_id})
                .execute()
            )
        except Exception as exc:
            return {
                "message_id": "",
                "message": f"Failed to send draft '{draft_id}': {exc}",
            }
        msg_id = result.get("id", "unknown")
        return {
            "message_id": msg_id,
            "message": f"Email sent (message ID: {msg_id}).",
        }
