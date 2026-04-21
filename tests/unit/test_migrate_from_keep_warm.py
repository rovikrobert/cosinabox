# ruff: noqa: I001
"""Tests for keep_warm note → commitment migration detection + query."""

from __future__ import annotations

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
