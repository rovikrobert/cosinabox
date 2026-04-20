from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob, _transcript_matches
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Matching algorithm — generic-name fixtures only (no real personal names).
# ---------------------------------------------------------------------------


CAL_START = datetime(2026, 4, 13, 10, 0, tzinfo=UTC)
CAL_END = datetime(2026, 4, 13, 10, 30, tzinfo=UTC)


class TestTranscriptMatchingTimeWindow:
    """Time match within ±30min of meeting start OR end is MANDATORY."""

    def test_no_date_never_matches(self):
        # Even a perfect title + attendee match must not match without a date.
        assert not _transcript_matches(
            {"title": "Q3 Strategy Review", "participants": ["bob@x.com"]},
            cal_title="Q3 Strategy Review",
            cal_emails={"bob@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )

    def test_unparseable_date_never_matches(self):
        assert not _transcript_matches(
            {"title": "Q3 Strategy Review", "participants": [], "date": "not-a-date"},
            cal_title="Q3 Strategy Review",
            cal_emails=set(),
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )

    def test_time_far_with_matching_title_does_not_match(self):
        # Same title and shared attendee, but date is 5 hours off → no match.
        assert not _transcript_matches(
            {
                "title": "Q3 Strategy Review",
                "participants": ["bob@x.com"],
                "date": "2026-04-13T15:00:00+00:00",
            },
            cal_title="Q3 Strategy Review",
            cal_emails={"bob@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )

    def test_within_window_of_start_matches(self):
        assert _transcript_matches(
            {
                "title": "Q3 Strategy Review",
                "participants": [],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Q3 Strategy Review",
            cal_emails=set(),
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )

    def test_within_window_of_end_matches(self):
        # Transcripts are typically created ~at meeting end, so test that
        # we accept times near cal_end too.
        assert _transcript_matches(
            {
                "title": "Q3 Strategy Review",
                "participants": [],
                "date": "2026-04-13T10:35:00+00:00",  # 5 min past end
            },
            cal_title="Q3 Strategy Review",
            cal_emails=set(),
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )


class TestTranscriptMatchingOwnerExclusion:
    """Owner's own name and email must not count toward title/attendee overlap."""

    def test_owner_name_in_title_alone_does_not_match(self):
        # cal "Alice/Bob"  vs  transcript "Alice & Carol", owner is alice.
        # The only overlapping >2-char word is "alice" → owner's name → excluded.
        # cal_emails only contain owner alice → excluded → no email overlap.
        # → time match alone is not enough.
        assert not _transcript_matches(
            {
                "title": "Alice & Carol",
                "participants": ["alice@x.com", "carol@y.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Alice/Bob",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_owner_email_alone_does_not_match(self):
        # cal_emails and t_participants only overlap on the owner's email.
        # No title overlap. → no match even though time is within window.
        assert not _transcript_matches(
            {
                "title": "Unrelated Sync",
                "participants": ["alice@x.com", "carol@y.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Quarterly Review",
            cal_emails={"alice@x.com", "dave@z.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_non_owner_attendee_overlap_with_time_match_does_match(self):
        # Shared non-owner attendee bob → match.
        assert _transcript_matches(
            {
                "title": "Unrelated",
                "participants": ["alice@x.com", "bob@y.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Quarterly Review",
            cal_emails={"alice@x.com", "bob@y.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )


class TestTranscriptMatchingTitle:
    def test_title_substring_with_time_matches(self):
        assert _transcript_matches(
            {
                "title": "Q3 Strategy Review (recorded)",
                "participants": [],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Q3 Strategy Review",
            cal_emails=set(),
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails=set(),
        )

    def test_word_overlap_excluding_owner_name(self):
        # "strategy" overlap (>2 chars), not an owner name → match.
        assert _transcript_matches(
            {
                "title": "Strategy session — alice & carol",
                "participants": [],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Strategy review",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )


class TestTranscriptTieBreak:
    """When multiple transcripts pass, pick the one closest to cal_start;
    further tiebreak by longer duration."""

    def test_picks_closest_to_start(self):
        from cosinabox.jobs.post_meeting_debrief import _pick_best_transcript

        far = {
            "id": "far",
            "title": "Quarterly Review",
            "participants": ["bob@y.com"],
            "date": "2026-04-13T10:25:00+00:00",  # 25 min off
            "duration": 30,
        }
        near = {
            "id": "near",
            "title": "Quarterly Review",
            "participants": ["bob@y.com"],
            "date": "2026-04-13T10:02:00+00:00",  # 2 min off
            "duration": 30,
        }
        best = _pick_best_transcript(
            [far, near],
            cal_start=CAL_START,
            cal_end=CAL_END,
        )
        assert best["id"] == "near"

    def test_tiebreak_by_longer_duration(self):
        from cosinabox.jobs.post_meeting_debrief import _pick_best_transcript

        short = {
            "id": "short",
            "title": "Quarterly Review",
            "participants": ["bob@y.com"],
            "date": "2026-04-13T10:05:00+00:00",
            "duration": 10,
        }
        long_ = {
            "id": "long",
            "title": "Quarterly Review",
            "participants": ["bob@y.com"],
            "date": "2026-04-13T10:05:00+00:00",
            "duration": 45,
        }
        best = _pick_best_transcript(
            [short, long_],
            cal_start=CAL_START,
            cal_end=CAL_END,
        )
        assert best["id"] == "long"


# ---------------------------------------------------------------------------
# Job-level behaviour
# ---------------------------------------------------------------------------


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


class TestPostMeetingDebriefTranscriptBody:
    """The sent message must NOT silently truncate transcript content
    mid-sentence. Either include the full text, or split across multiple
    send calls at sentence boundaries."""

    def _make_event_and_transcript(self, sentence_count=12):
        from cosinabox.tools.google.calendar import CalendarEvent

        now = datetime.now(UTC)
        ended = now - timedelta(minutes=20)
        evt = CalendarEvent(
            id="evt-long",
            summary="Quarterly Strategy Review",
            start=ended - timedelta(minutes=30),
            end=ended,
            attendees=["bob@y.com"],
        )
        # Long, sentence-rich transcript — first 10 sentences combined are
        # well over 800 chars so the old code would slice mid-sentence.
        long_sentence = (
            "We discussed in detail the proposed roadmap for the next two "
            "quarters and aligned on the highest-priority initiatives across "
            "engineering, product, and design while reviewing dependencies."
        )
        sentences = [{"text": long_sentence} for _ in range(sentence_count)]
        return evt, sentences

    def test_long_transcript_not_truncated_mid_sentence(self, mem):
        evt, sentences = self._make_event_and_transcript()

        cal = MagicMock()
        cal.list_events.return_value = [evt]

        ff = MagicMock()
        ff.list_recent_meetings.return_value = [
            {
                "id": "t1",
                "title": "Quarterly Strategy Review",
                "participants": ["bob@y.com"],
                "date": (evt.end - timedelta(minutes=2)).isoformat(),
            }
        ]
        ff.get_transcript.return_value = {"sentences": sentences}

        sends: list[str] = []

        def capture(msg: str) -> None:
            sends.append(msg)

        job = PostMeetingDebriefJob(
            calendar=cal,
            fireflies=ff,
            db=mem,
            send_fn=capture,
            skip_titles=[],
            owner_emails=["alice@x.com"],
        )
        job.run()

        assert sends, "expected at least one Telegram send"
        full_body = "\n----\n".join(sends)

        # The original sentence text must appear in full at least once,
        # un-mutilated by a mid-sentence slice.
        full_sentence = (
            "We discussed in detail the proposed roadmap for the next two "
            "quarters and aligned on the highest-priority initiatives across "
            "engineering, product, and design while reviewing dependencies."
        )
        assert full_sentence in full_body, (
            "Transcript content was truncated mid-sentence. Got body:\n" + full_body
        )

        # No individual send may exceed Telegram's hard limit.
        for s in sends:
            assert len(s) <= 4096, f"single message exceeds Telegram limit: {len(s)}"
