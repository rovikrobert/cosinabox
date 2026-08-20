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


class TestTranscriptMatchingTitleTokens:
    """Title tokenisation.

    Two properties matter. Short alphanumeric tokens ("q3", "v2", "f1") are
    often the most distinctive word in a meeting title and must survive the
    noise filter — a plain length cutoff drops exactly the token that tells
    two adjacent meetings apart. And tokens must split on punctuation, so a
    title written "Q3-planning" can still overlap one written "Q3 planning".

    Bare numbers and short pure-alpha words stay filtered: room numbers,
    headcounts and stopwords carry no topic signal.
    """

    def test_short_alphanumeric_token_overlap_matches(self):
        # The only word shared by the two titles is "q3" — every other token
        # differs, participants are owner-only, and neither title contains the
        # other. A length-only filter drops "q3" and loses a valid pairing.
        assert _transcript_matches(
            {
                "title": "Q3 planning — budget, venue, and headcount with Bob",
                "participants": ["alice@x.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="AC/Alice - Q3 Offsite",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_punctuation_glued_tokens_still_overlap(self):
        # "Q3-planning" must split into "q3" + "planning", and "budget," must
        # shed its comma, or neither can ever match its unpunctuated twin.
        assert _transcript_matches(
            {
                "title": "budget, planning",
                "participants": ["alice@x.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Q3-planning",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_bare_number_overlap_does_not_match(self):
        # "10" is a room number or a headcount, never a topic. Keeping short
        # tokens must not degrade into matching on digits alone.
        assert not _transcript_matches(
            {
                "title": "Retro 10",
                "participants": ["alice@x.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Standup 10",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_short_alpha_word_overlap_does_not_match(self):
        # Two-letter pure-alpha tokens ("go", initials like "ac") are noise.
        assert not _transcript_matches(
            {
                "title": "Go retro",
                "participants": ["alice@x.com"],
                "date": "2026-04-13T10:05:00+00:00",
            },
            cal_title="Go standup",
            cal_emails={"alice@x.com"},
            cal_start=CAL_START,
            cal_end=CAL_END,
            owner_emails={"alice@x.com"},
        )

    def test_short_token_does_not_bypass_the_time_window(self):
        # A shared "q3" must not rescue a transcript from a different slot.
        assert not _transcript_matches(
            {
                "title": "Q3 planning — budget, venue, and headcount with Bob",
                "participants": ["alice@x.com"],
                "date": "2026-04-13T15:00:00+00:00",
            },
            cal_title="AC/Alice - Q3 Offsite",
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


class TestPersistsToDmSession:
    """When dm_session+memory are wired, the debrief text the user sees on
    Telegram must also land in the DM session as role=assistant. This is what
    lets the agent recall what it sent when the user replies "wrong meeting"
    or "tell me more about the action items" in their DM.
    """

    def _calendar_with_one_ended_meeting(self, summary: str = "Project Sync"):
        """Build a calendar mock with one event that ended ~20min ago.

        Two attendees because `is_prep_worthy` (shipped in PR #54) skips
        zero-attendee events as solo blocks.
        """
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
                attendees=["a@example.com", "b@example.com"],
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
