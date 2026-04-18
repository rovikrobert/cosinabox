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
            gmail=mock_gmail,
            db=mem,
            send_alert=MagicMock(),
            urgent_senders=[],
            poll_interval_minutes=5,
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
            gmail=mock_gmail,
            db=mem,
            send_alert=MagicMock(),
            urgent_senders=[],
            poll_interval_minutes=5,
        )
        job.run()
        # The query passed to gmail.search must use epoch seconds, not a date.
        call_args = mock_gmail.search.call_args
        query = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        assert query.startswith("after:")
        after_val = query.split("after:", 1)[1].split()[0]
        # Must be integer epoch seconds, not YYYY/MM/DD.
        assert after_val.isdigit(), f"Expected epoch seconds after:..., got after:{after_val}"
        # Sanity: at least 10 digits (epoch > 2001)
        assert len(after_val) >= 10

    def test_dedup_prevents_double_alert(self, mem):
        from cosinabox.tools.google.gmail import GmailMessage

        msg = GmailMessage(
            id="m1",
            sender="ceo@bigcorp.com",
            subject="Urgent",
            snippet="Help",
            date="2026-04-12",
        )
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = [msg]
        alert = MagicMock()

        job = InboundEmailCheckJob(
            gmail=mock_gmail,
            db=mem,
            send_alert=alert,
            urgent_senders=["@bigcorp.com"],
        )
        job.run()
        assert alert.call_count == 1

        job.run()
        assert alert.call_count == 1  # still 1, not 2


class TestPersistsToDmSession:
    """When dm_session+memory are wired, the urgent-email alert the user sees
    on Telegram must also land in the DM session as role=assistant. This is
    what lets the agent recall the alert when the user replies "draft a
    reply" or "who else got copied" in their DM.
    """

    def _make_urgent_msg(self, sender: str = "alice@bigcorp.com"):
        from cosinabox.tools.google.gmail import GmailMessage

        return GmailMessage(
            id="m-persist-1",
            sender=sender,
            subject="Project status",
            snippet="quick update on the launch",
            date="2026-04-12",
        )

    def test_alert_text_persisted_to_dm_session_as_assistant(self, mem):
        msg = self._make_urgent_msg()
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = [msg]
        sent: list[str] = []

        job = InboundEmailCheckJob(
            gmail=mock_gmail,
            db=mem,
            send_alert=sent.append,
            urgent_senders=["@bigcorp.com"],
            memory=mem,
            dm_session="dm-12345",
        )
        job.run()

        assert sent, "send_alert should have been called"
        history = mem.recent_messages(session_id="dm-12345")
        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert assistant_msgs, "alert text should be persisted as assistant"
        # The DM-recall use case requires the EXACT text the user saw to be
        # findable, so we assert the sender (the most distinctive signal a
        # follow-up reply would reference) survives the persist.
        joined = "\n".join(m["content"] for m in assistant_msgs)
        assert "alice@bigcorp.com" in joined

    def test_no_persist_when_dm_session_not_configured(self, mem):
        """Backwards-compat: jobs constructed without dm_session/memory
        must still alert and not error. (Existing OSS user repos may not
        pass these params yet.)"""
        msg = self._make_urgent_msg("bob@bigcorp.com")
        mock_gmail = MagicMock()
        mock_gmail.search.return_value = [msg]
        sent: list[str] = []

        job = InboundEmailCheckJob(
            gmail=mock_gmail,
            db=mem,
            send_alert=sent.append,
            urgent_senders=["@bigcorp.com"],
        )
        job.run()

        assert sent, "send_alert should still fire when DM persist is off"
        assert mem.recent_messages(session_id="dm-anything") == []
