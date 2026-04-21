# ruff: noqa: I001, E402
"""Tests for keep_warm note → commitment migration detection + query."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cosinabox.commitments.migrate_from_keep_warm import looks_like_commitment


@pytest.mark.parametrize(
    "text",
    [
        "Send proposal by Friday",
        "Follow up by EOD Monday",
        "Reply before next week",
        "Submit SOW by March 15",
        "Share the deck by Tuesday 5pm",
        "Email intro before EOW",
        "Respond by Q2",
        "Deliver draft next month",
        "Ping in 3 days",
        "Call back by Jan 15",
        "Follow up on Friday",
    ],
)
def test_looks_like_commitment_matches_deadline_phrases(text: str) -> None:
    matched = looks_like_commitment(text)
    assert matched is not None, f"expected match for: {text!r}"
    # Matched substring is from the input
    assert matched.lower() in text.lower()


@pytest.mark.parametrize(
    "text",
    [
        "SOW with Daniel is a key priority",
        "Lead Investor",
        "triathlete, son Oliver just started college",
        "introduced by Sarah in 2023; mentor for 5y",
        "SVP at Acme, owns Series B decision",
        "prospective Series A lead",
        "warm intro from Jake",
        "ex-colleague from Stripe",
        "",
        "    ",
    ],
)
def test_looks_like_commitment_ignores_pure_status(text: str) -> None:
    assert looks_like_commitment(text) is None, f"false positive on: {text!r}"


def test_looks_like_commitment_none_input() -> None:
    assert looks_like_commitment(None) is None


def test_looks_like_commitment_returns_first_match_substring() -> None:
    matched = looks_like_commitment("SOW is key. Send proposal by Friday. Thanks.")
    assert matched is not None
    assert "Friday" in matched or "by" in matched.lower()


def _kw_person(
    *,
    name: str,
    record_id: str,
    note: str | None,
    days_since: int | None = 10,
    cadence_days: int = 14,
) -> SimpleNamespace:
    """Stand-in for attio.KeepWarmPerson with the fields we need."""
    return SimpleNamespace(
        name=name,
        record_id=record_id,
        cadence_days=cadence_days,
        note=note,
        last_interaction=None,
        days_since=days_since,
    )


class _StubAttio:
    def __init__(self, people: list[SimpleNamespace]) -> None:
        self.people = people

    def list_keep_warm(self) -> list[SimpleNamespace]:
        return list(self.people)


def test_list_flagged_keep_warm_notes_returns_only_flagged_rows() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    attio = _StubAttio(
        [
            _kw_person(name="Sarah", record_id="r1", note="Lead Investor"),
            _kw_person(name="Daniel", record_id="r2", note="Send proposal by Friday"),
            _kw_person(name="Amy", record_id="r3", note=None),
            _kw_person(name="Tom", record_id="r4", note="ex-colleague from Stripe"),
            _kw_person(name="Jane", record_id="r5", note="Follow up next week"),
        ]
    )
    flagged = list_flagged_keep_warm_notes(attio)
    names = {row["person"] for row in flagged}
    assert names == {"Daniel", "Jane"}


def test_list_flagged_keep_warm_notes_row_shape() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    attio = _StubAttio([_kw_person(name="Daniel", record_id="r2", note="Send proposal by Friday")])
    [row] = list_flagged_keep_warm_notes(attio)
    assert row["person"] == "Daniel"
    assert row["record_id"] == "r2"
    assert row["note"] == "Send proposal by Friday"
    assert row["regex_matches"] and all(
        m in row["note"].lower() or m in row["note"] for m in row["regex_matches"]
    )
    assert row["days_since"] == 10
    assert row["cadence_days"] == 14


def test_list_flagged_keep_warm_notes_handles_attio_error() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    class _Broken:
        def list_keep_warm(self) -> list[SimpleNamespace]:
            raise RuntimeError("Attio 500")

    assert list_flagged_keep_warm_notes(_Broken()) == []
