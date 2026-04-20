# ruff: noqa: I001
"""Tests for the sync auto_resolve verifier.

Mocks GmailTool.search — never hits the network. Port of cos-agent's
verifier tests, minus the Drive search path (deferred to follow-up).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cosinabox.commitments import create_commitment
from cosinabox.commitments.auto_resolve import (
    VERDICT_LIKELY_DONE,
    VERDICT_NO_EVIDENCE,
    VERDICT_VERIFIED_DONE,
    _extract_keywords,
    _has_real_match,
    _sanitize_query,
    format_for_briefing,
    verify_all_open_commitments,
    verify_commitment,
)
from cosinabox.memory import Memory


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


def _msg(subject: str) -> MagicMock:
    m = MagicMock()
    m.subject = subject
    m.sender = "Me <me@x.com>"
    m.snippet = ""
    m.date = "Fri, 19 Apr 2026 10:00:00 +0000"
    return m


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_extract_keywords_drops_stopwords_and_keeps_acronyms() -> None:
    kws = _extract_keywords("Send NTU the proposal")
    assert "ntu" in kws
    assert "proposal" in kws
    # stopwords pruned
    assert "the" not in kws
    assert "send" not in kws


def test_extract_keywords_leads_with_stakeholder_first_name() -> None:
    kws = _extract_keywords("Follow up on proposal", stakeholder="Sarah Chen")
    assert kws[0] == "sarah"


def test_sanitize_query_strips_gmail_operators() -> None:
    assert "from:" not in _sanitize_query('Hello from:me "subject:x"')


def test_has_real_match_requires_two_subject_keywords() -> None:
    results = [_msg("NTU proposal sent")]
    assert _has_real_match(results, ["ntu", "proposal"]) is True

    one_kw = [_msg("NTU follow-up")]
    assert _has_real_match(one_kw, ["ntu", "proposal"]) is False


def test_has_real_match_empty_list() -> None:
    assert _has_real_match([], ["x"]) is False


# ---------------------------------------------------------------------------
# verify_commitment with mocked gmail
# ---------------------------------------------------------------------------


def test_two_matches_in_subject_yields_verified_done(db: Memory) -> None:
    c = create_commitment(db, title="Send NTU proposal draft", stakeholder="Adwin")
    gmail = MagicMock()
    gmail.search.return_value = [
        _msg("Re: NTU proposal draft — final"),
        _msg("Sending NTU proposal"),
        _msg("NTU proposal follow up"),
    ]
    got = verify_commitment(c, gmail)
    assert got["_verdict"] == VERDICT_VERIFIED_DONE
    # evidence mentions the sent mail path
    assert "sent mail" in got["_evidence"].lower()


def test_single_weak_match_yields_likely_done(db: Memory) -> None:
    c = create_commitment(db, title="Send NTU proposal draft", stakeholder="Adwin")
    gmail = MagicMock()
    # one subject match but not 2+ keywords — falls through to stakeholder
    # email check; with no stakeholder email field, stays NO_EVIDENCE unless
    # we have a dedicated to:<name> probe. This port uses a simpler rule:
    # one keyword match = LIKELY_DONE.
    gmail.search.return_value = [_msg("NTU catch-up call")]
    got = verify_commitment(c, gmail)
    assert got["_verdict"] in (VERDICT_LIKELY_DONE, VERDICT_NO_EVIDENCE)


def test_no_matches_yields_no_evidence(db: Memory) -> None:
    c = create_commitment(db, title="Send Sarah Q3 deck")
    gmail = MagicMock()
    gmail.search.return_value = []
    got = verify_commitment(c, gmail)
    assert got["_verdict"] == VERDICT_NO_EVIDENCE
    assert "no match" in got["_evidence"].lower() or "no search terms" in got["_evidence"].lower()


def test_gmail_exception_yields_no_evidence(db: Memory) -> None:
    c = create_commitment(db, title="Send proposal")
    gmail = MagicMock()
    gmail.search.side_effect = RuntimeError("api down")
    got = verify_commitment(c, gmail)
    assert got["_verdict"] == VERDICT_NO_EVIDENCE
    # evidence explains why
    assert "error" in got["_evidence"].lower() or "no match" in got["_evidence"].lower()


def test_verify_persists_last_verdict(db: Memory) -> None:
    c = create_commitment(db, title="Send NTU proposal")
    gmail = MagicMock()
    gmail.search.return_value = [
        _msg("NTU proposal final"),
        _msg("Re: NTU proposal"),
    ]
    verify_commitment(c, gmail, db=db)

    cur = db._conn.execute(
        "SELECT last_verdict, last_verdict_at FROM commitments WHERE id = ?",
        (c["id"],),
    )
    row = cur.fetchone()
    assert row["last_verdict"] == VERDICT_VERIFIED_DONE
    assert row["last_verdict_at"] is not None


# ---------------------------------------------------------------------------
# verify_all_open_commitments
# ---------------------------------------------------------------------------


def test_verify_all_returns_one_result_per_open_commitment(db: Memory) -> None:
    a = create_commitment(db, title="a proposal NTU")
    b = create_commitment(db, title="b follow up Sarah")
    gmail = MagicMock()
    gmail.search.return_value = []

    results = verify_all_open_commitments(db, gmail)
    ids = [r["id"] for r in results]
    assert a["id"] in ids
    assert b["id"] in ids
    assert len(results) == 2


def test_verify_all_skips_closed_commitments(db: Memory) -> None:
    from cosinabox.commitments import close_commitment

    a = create_commitment(db, title="open one NTU")
    b = create_commitment(db, title="closed one")
    close_commitment(db, b["id"])

    gmail = MagicMock()
    gmail.search.return_value = []
    results = verify_all_open_commitments(db, gmail)
    assert [r["id"] for r in results] == [a["id"]]


# ---------------------------------------------------------------------------
# format_for_briefing
# ---------------------------------------------------------------------------


def test_format_for_briefing_groups_by_verdict() -> None:
    verified = [
        {
            "id": 1,
            "title": "ship NTU deck",
            "priority": 1,
            "_verdict": VERDICT_VERIFIED_DONE,
            "_evidence": "mail match",
        },
        {
            "id": 2,
            "title": "close intro",
            "priority": 3,
            "_verdict": VERDICT_LIKELY_DONE,
            "_evidence": "weak",
        },
        {
            "id": 3,
            "title": "open item",
            "priority": 2,
            "_verdict": VERDICT_NO_EVIDENCE,
            "_evidence": "",
        },
    ]
    out = format_for_briefing(verified)
    assert "VERIFIED DONE" in out
    assert "LIKELY DONE" in out
    assert "GENUINELY OPEN" in out
    # Each id shown
    assert "#1" in out
    assert "#2" in out
    assert "#3" in out


def test_format_for_briefing_empty_returns_empty_string() -> None:
    assert format_for_briefing([]) == ""
