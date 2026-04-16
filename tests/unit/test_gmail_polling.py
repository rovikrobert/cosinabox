from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cosinabox.jobs.inbound_email_check import InboundEmailCheckJob, is_urgent_sender
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestUrgencyMatching:
    def test_exact_match(self):
        senders = ["ceo@bigcorp.com"]
        assert is_urgent_sender("ceo@bigcorp.com", senders) is True

    def test_domain_match(self):
        senders = ["@bigcorp.com"]
        assert is_urgent_sender("anyone@bigcorp.com", senders) is True

    def test_no_match(self):
        senders = ["@bigcorp.com"]
        assert is_urgent_sender("random@gmail.com", senders) is False

    def test_empty_senders(self):
        assert is_urgent_sender("anyone@x.com", []) is False

    def test_case_insensitive(self):
        senders = ["CEO@BigCorp.com"]
        assert is_urgent_sender("ceo@bigcorp.com", senders) is True


class TestInboundEmailCheckJob:
    def test_skips_when_gmail_is_none(self, mem):
        job = InboundEmailCheckJob(gmail=None, db=mem, send_alert=MagicMock(), urgent_senders=[])
        result = job.run()
        assert "skipped" in result.lower() or result == ""

    def test_first_run_uses_recent_window(self, mem):
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = []
        job = InboundEmailCheckJob(
            gmail=mock_gmail, db=mem, send_alert=MagicMock(),
            urgent_senders=[], poll_interval_minutes=5,
        )
        job.run()
        mock_gmail.search.assert_called()

    def test_search_query_uses_epoch_seconds_not_date(self, mem):
        """Plan 4 polish item 9: ``after:YYYY/MM/DD`` over-fetches the whole
        day and truncates at the 50-msg cap. Switching to ``after:<epoch>``
        narrows to the actual last_check timestamp."""
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = []
        job = InboundEmailCheckJob(
            gmail=mock_gmail, db=mem, send_alert=MagicMock(),
            urgent_senders=[], poll_interval_minutes=5,
        )
        job.run()
        # The query passed to gmail.search must use epoch seconds, not a date.
        call_args = mock_gmail.search.call_args
        query = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        assert query.startswith("after:")
        after_val = query.split("after:", 1)[1].split()[0]
        # Must be integer epoch seconds, not YYYY/MM/DD.
        assert after_val.isdigit(), (
            f"Expected epoch seconds after:..., got after:{after_val}"
        )
        # Sanity: at least 10 digits (epoch > 2001)
        assert len(after_val) >= 10

    def test_dedup_prevents_double_alert(self, mem):
        from cosinabox.tools.google.gmail import GmailMessage
        msg = GmailMessage(id="m1", sender="ceo@bigcorp.com", subject="Urgent", snippet="Help", date="2026-04-12")
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = [msg]
        alert = MagicMock()

        job = InboundEmailCheckJob(
            gmail=mock_gmail, db=mem, send_alert=alert,
            urgent_senders=["@bigcorp.com"],
        )
        job.run()
        assert alert.call_count == 1

        job.run()
        assert alert.call_count == 1  # still 1, not 2
