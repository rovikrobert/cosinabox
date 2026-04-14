from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cosinabox.jobs.crm_email_sync import CrmEmailSyncJob


class TestCrmEmailSyncJob:
    def test_skips_when_gmail_none(self):
        job = CrmEmailSyncJob(gmail=None, attio=MagicMock())
        result = job.run()
        assert "skipped" in result.lower()

    def test_skips_when_attio_none(self):
        job = CrmEmailSyncJob(gmail=MagicMock(), attio=None)
        result = job.run()
        assert "skipped" in result.lower()

    def test_no_sent_emails_reports_zero(self):
        gmail = MagicMock()
        gmail.search.return_value = []
        attio = MagicMock()
        job = CrmEmailSyncJob(gmail=gmail, attio=attio)
        result = job.run()
        assert "0" in result

    def test_updates_matching_recipients(self):
        from cosinabox.tools.google.gmail import GmailMessage
        gmail = MagicMock()
        gmail.search.return_value = [
            GmailMessage(id="m1", sender="me@co.com", subject="Hi", snippet="", date="2026-04-12"),
        ]

        attio = MagicMock()
        attio.search_people.return_value = [{"id": "p1", "name": "Alice"}]
        attio.update_person.return_value = {"id": "p1"}

        job = CrmEmailSyncJob(gmail=gmail, attio=attio)
        job._get_recipients = MagicMock(return_value=["alice@example.com"])
        result = job.run()
        assert "1" in result
        attio.update_person.assert_called_once()

    def test_continues_on_individual_failure(self):
        from cosinabox.tools.google.gmail import GmailMessage
        gmail = MagicMock()
        gmail.search.return_value = [
            GmailMessage(id="m1", sender="me@co.com", subject="Hi", snippet="", date="2026-04-12"),
        ]

        attio = MagicMock()
        attio.search_people.side_effect = Exception("API error")

        job = CrmEmailSyncJob(gmail=gmail, attio=attio)
        job._get_recipients = MagicMock(return_value=["alice@example.com"])
        result = job.run()
        # Should not crash — should report failure
        assert "fail" in result.lower() or "0" in result
