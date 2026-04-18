from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob, _transcript_matches
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestTranscriptMatching:
    def test_title_substring_match(self):
        assert _transcript_matches(
            {"title": "Q3 Strategy Review", "participants": []},
            cal_title="strategy review",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_shared_words_match(self):
        assert _transcript_matches(
            {"title": "Sprint Planning Meeting", "participants": []},
            cal_title="Planning Session",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_generic_title_requires_two_criteria(self):
        assert not _transcript_matches(
            {"title": "Sync", "participants": [], "date": "2026-04-13T15:00:00"},
            cal_title="Sync",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_attendee_plus_time_matches_generic(self):
        assert _transcript_matches(
            {"title": "Sync", "participants": ["alice@x.com"], "date": "2026-04-13T10:05:00+00:00"},
            cal_title="Sync",
            cal_emails={"alice@x.com"},
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_no_match(self):
        assert not _transcript_matches(
            {"title": "Unrelated", "participants": []},
            cal_title="Budget Review",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )


class TestPostMeetingDebriefJob:
    def test_skips_when_calendar_none(self, mem):
        job = PostMeetingDebriefJob(
            calendar=None,
            fireflies=None,
            db=mem,
            send_fn=MagicMock(),
            skip_titles=[],
        )
        result = job.run()
        assert "skipped" in result.lower()

    def test_skips_already_debriefed(self, mem):
        mem._conn.execute(
            "INSERT INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            ("e1", datetime.now(UTC).isoformat()),
        )
        mem._conn.commit()

        from cosinabox.tools.google.calendar import CalendarEvent

        now = datetime.now(UTC)
        ended = now - timedelta(minutes=20)
        cal = MagicMock()
        cal.list_events.return_value = [
            CalendarEvent(
                id="e1",
                summary="Standup",
                start=ended - timedelta(minutes=30),
                end=ended,
            ),
        ]

        job = PostMeetingDebriefJob(
            calendar=cal,
            fireflies=None,
            db=mem,
            send_fn=MagicMock(),
            skip_titles=[],
        )
        result = job.run()
        assert "0" in result


class TestPersistsToDmSession:
    """When dm_session+memory are wired, the debrief text the user sees on
    Telegram must also land in the DM session as role=assistant. This is what
    lets the agent recall what it sent when the user replies "wrong meeting"
    or "tell me more about the action items" in their DM.
    """

    def _calendar_with_one_ended_meeting(self, summary: str = "Project Sync"):
        """Build a calendar mock with one event that ended ~20min ago."""
        from cosinabox.tools.google.calendar import CalendarEvent

        now = datetime.now(UTC)
        ended = now - timedelta(minutes=20)
        cal = MagicMock()
        cal.list_events.return_value = [
            CalendarEvent(
                id="evt-persist-1",
                summary=summary,
                start=ended - timedelta(minutes=30),
                end=ended,
            ),
        ]
        return cal

    def test_debrief_text_persisted_to_dm_session_as_assistant(self, mem):
        cal = self._calendar_with_one_ended_meeting("Project Sync")
        sent: list[str] = []

        job = PostMeetingDebriefJob(
            calendar=cal,
            fireflies=None,
            db=mem,
            send_fn=sent.append,
            skip_titles=[],
            dm_session="dm-12345",
            memory=mem,
        )
        result = job.run()

        assert "1" in result
        # The exact body sent to the user must also be in the DM session.
        assert sent, "send_fn should have been called"
        history = mem.recent_messages(session_id="dm-12345")
        assert history, "DM session should contain the debrief text"
        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert assistant_msgs, "Persisted message should be role=assistant"
        # The DM-recall use case requires the EXACT text the user saw to be
        # findable, so we assert the meeting title (the most distinctive
        # signal a follow-up reply would reference) survives the persist.
        joined = "\n".join(m["content"] for m in assistant_msgs)
        assert "Project Sync" in joined

    def test_no_persist_when_dm_session_not_configured(self, mem):
        """Backwards-compat: jobs constructed without dm_session/memory
        must still send and not error. (Existing call sites in OSS user
        repos may not pass these params yet.)"""
        cal = self._calendar_with_one_ended_meeting("Standup")
        sent: list[str] = []

        job = PostMeetingDebriefJob(
            calendar=cal,
            fireflies=None,
            db=mem,
            send_fn=sent.append,
            skip_titles=[],
        )
        result = job.run()

        assert "1" in result
        assert sent, "send_fn should still be called when DM persist is off"
        # No DM session key should have been written.
        assert mem.recent_messages(session_id="dm-anything") == []
