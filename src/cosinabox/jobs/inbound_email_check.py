"""Gmail polling — check for new inbound email, alert on urgent senders."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)


def is_urgent_sender(sender_email: str, urgent_senders: list[str]) -> bool:
    """Check if sender matches the urgency list (exact or domain match)."""
    email_lower = sender_email.lower().strip()
    for pattern in urgent_senders:
        p = pattern.lower().strip()
        if p.startswith("@"):
            if email_lower.endswith(p):
                return True
        else:
            if email_lower == p:
                return True
    return False


class InboundEmailCheckJob(Job):
    name = "inbound_email_check"

    def __init__(
        self,
        *,
        gmail: Any | None,
        db: Any,
        send_alert: Callable[[str], None],
        urgent_senders: list[str] | None = None,
        poll_interval_minutes: int = 5,
    ) -> None:
        self.gmail = gmail
        self.db = db
        self.send_alert = send_alert
        self.urgent_senders = urgent_senders or []
        self.poll_interval_minutes = poll_interval_minutes

    def run(self, context: Any = None) -> str:
        if self.gmail is None:
            return "Gmail not configured — skipped"

        cur = self.db._conn.execute(
            "SELECT last_check_ts FROM gmail_poll_state WHERE account_index = 0",
        )
        row = cur.fetchone()
        if row:
            last_check = row["last_check_ts"]
        else:
            last_check = (
                datetime.now(UTC) - timedelta(minutes=self.poll_interval_minutes)
            ).isoformat()

        check_dt = datetime.fromisoformat(last_check)
        # Use epoch seconds so `after:` narrows to the exact last-check
        # moment instead of fetching the entire day (the date-level query
        # would hit the 50-msg cap on busy inboxes and silently drop
        # messages). Gmail documents `after:<unix-ts>` as a valid operator.
        if check_dt.tzinfo is None:
            check_dt = check_dt.replace(tzinfo=UTC)
        after_epoch = int(check_dt.timestamp())

        messages = self.gmail.search(f"after:{after_epoch}", max_results=50)

        poll_start_ts = datetime.now(UTC).isoformat()
        alert_count = 0
        for msg in messages:
            cur = self.db._conn.execute(
                "SELECT 1 FROM processed_message_ids WHERE message_id = ?",
                (msg.id,),
            )
            if cur.fetchone():
                continue

            ts = datetime.now(UTC).isoformat()
            self.db._conn.execute(
                "INSERT OR IGNORE INTO processed_message_ids (message_id, created_at) "
                "VALUES (?, ?)",
                (msg.id, ts),
            )

            if is_urgent_sender(msg.sender, self.urgent_senders):
                self.send_alert(
                    f"[URGENT EMAIL] From: {msg.sender} | Subject: {msg.subject}\n{msg.snippet}"
                )
                alert_count += 1

        # Advance poll state once per run — even when no messages arrived —
        # so the next poll's `after:` window moves forward. Without this, a
        # quiet inbox would re-query the same window on every run.
        self.db._conn.execute(
            "INSERT OR REPLACE INTO gmail_poll_state (account_index, last_check_ts) VALUES (0, ?)",
            (poll_start_ts,),
        )
        self.db._conn.commit()

        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        self.db._conn.execute(
            "DELETE FROM processed_message_ids WHERE created_at < ?",
            (cutoff,),
        )
        self.db._conn.commit()

        return f"Checked {len(messages)} emails, {alert_count} urgent alerts sent"
