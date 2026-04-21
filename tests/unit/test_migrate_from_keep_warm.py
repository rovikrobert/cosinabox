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
