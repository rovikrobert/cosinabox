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
            cal_title="strategy review", cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_shared_words_match(self):
        assert _transcript_matches(
            {"title": "Sprint Planning Meeting", "participants": []},
            cal_title="Planning Session", cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_generic_title_requires_two_criteria(self):
        assert not _transcript_matches(
            {"title": "Sync", "participants": [], "date": "2026-04-13T15:00:00"},
            cal_title="Sync", cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_attendee_plus_time_matches_generic(self):
        assert _transcript_matches(
            {"title": "Sync", "participants": ["alice@x.com"], "date": "2026-04-13T10:05:00+00:00"},
            cal_title="Sync", cal_emails={"alice@x.com"},
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_no_match(self):
        assert not _transcript_matches(
            {"title": "Unrelated", "participants": []},
            cal_title="Budget Review", cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )


class TestPostMeetingDebriefJob:
    def test_skips_when_calendar_none(self, mem):
        job = PostMeetingDebriefJob(
            calendar=None, fireflies=None, db=mem,
            send_fn=MagicMock(), skip_titles=[],
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
            CalendarEvent(id="e1", summary="Standup", start=ended - timedelta(minutes=30), end=ended),
        ]

        job = PostMeetingDebriefJob(
            calendar=cal, fireflies=None, db=mem,
            send_fn=MagicMock(), skip_titles=[],
        )
        result = job.run()
        assert "0" in result
