"""CRM sync — update Attio last_interaction from today's sent emails."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)


class CrmEmailSyncJob(Job):
    name = "crm_email_sync"

    def __init__(self, *, gmail: Any | None, attio: Any | None) -> None:
        self.gmail = gmail
        self.attio = attio

    def _get_recipients(self, msg: Any) -> list[str]:
        """Extract To + Cc recipients for a GmailMessage.

        In production, delegates to ``gmail.get_recipients(msg.id)`` which
        fetches the message's To/Cc headers via the Gmail API. Tests can
        override this method directly.

        Returns ``[]`` if the adapter does not expose ``get_recipients`` —
        keeping the job a no-op rather than crashing when paired with a
        non-standard adapter.
        """
        get_recipients = getattr(self.gmail, "get_recipients", None)
        if not callable(get_recipients):
            return []
        try:
            result = get_recipients(msg.id)
        except Exception:
            logger.warning(
                "get_recipients failed for %s",
                getattr(msg, "id", "?"),
                exc_info=True,
            )
            return []
        return list(result or [])

    def run(self, context: Any = None) -> str:
        if self.gmail is None:
            return "Gmail not configured — skipped"
        if self.attio is None:
            return "Attio not configured — skipped"

        today = datetime.now(UTC).strftime("%Y/%m/%d")
        sent = self.gmail.search(f"in:sent after:{today}", max_results=100)

        updated = 0
        failed = 0
        consecutive_429s = 0

        seen_emails: set[str] = set()
        aborted = False
        for msg in sent:
            if aborted:
                break
            recipients = self._get_recipients(msg)
            for email in recipients:
                if email in seen_emails:
                    continue
                seen_emails.add(email)

                try:
                    people = self.attio.search_people(email)
                except Exception:
                    logger.warning("Attio search failed for %s", email, exc_info=True)
                    failed += 1
                    continue

                if not people:
                    continue

                person_id = people[0].get("id", "")
                if not person_id:
                    continue

                try:
                    self.attio.update_person(
                        person_id,
                        {"last_interaction": [{"value": datetime.now(UTC).isoformat()}]},
                    )
                    updated += 1
                    consecutive_429s = 0
                except Exception as exc:
                    failed += 1
                    if "429" in str(exc):
                        consecutive_429s += 1
                        if consecutive_429s >= 3:
                            logger.warning("CRM sync aborted: 3 consecutive rate limits")
                            aborted = True
                            break
                        time.sleep(2)
                    else:
                        logger.warning("Attio update failed for %s", email, exc_info=True)

        total = updated + failed
        if total == 0:
            return "CRM sync: 0 interactions (no sent emails today)"
        return f"CRM sync: {updated}/{total} interactions updated, {failed} failed"
