"""Tests for is_approval — tightened per Plan 4 polish item 7.

- Exact-match normalised form (strip + lowercase + whitespace-collapse)
- Must have pending tool in session
- "yes but actually no" must NOT approve
- "k"/"ok" with no pending tool must NOT approve
"""

from __future__ import annotations

from cosinabox.app import is_approval


class TestIsApprovalExactMatch:
    def test_yes_alone_approves(self):
        assert is_approval("yes", has_pending_tool=True) is True

    def test_yes_with_trailing_whitespace_approves(self):
        assert is_approval("  yes  \n", has_pending_tool=True) is True

    def test_yes_case_insensitive(self):
        assert is_approval("YES", has_pending_tool=True) is True
        assert is_approval("Ok", has_pending_tool=True) is True

    def test_multi_word_phrase_approves(self):
        assert is_approval("go ahead", has_pending_tool=True) is True
        assert is_approval("Go Ahead", has_pending_tool=True) is True

    def test_multi_word_with_collapsed_whitespace(self):
        # "go  ahead" with double space still approves after collapse.
        assert is_approval("go   ahead", has_pending_tool=True) is True


class TestIsApprovalRejectsSuffixes:
    def test_yes_but_actually_no_rejected(self):
        """Previously broke: first-word check accepted 'yes but actually no'."""
        assert is_approval("yes but actually no", has_pending_tool=True) is False

    def test_yes_please_rejected_now(self):
        """Trade-off: tightening loses 'yes please' but gains safety.
        If users want flexibility, they can use 'yes' or 'ok'."""
        assert is_approval("yes please", has_pending_tool=True) is False

    def test_ok_thanks_rejected(self):
        assert is_approval("ok thanks", has_pending_tool=True) is False

    def test_no_but_yes_rejected(self):
        assert is_approval("no but yes", has_pending_tool=True) is False


class TestIsApprovalRequiresPendingTool:
    def test_yes_with_no_pending_returns_false(self):
        """Bare approval word with nothing waiting must not count."""
        assert is_approval("yes", has_pending_tool=False) is False

    def test_ok_with_no_pending_returns_false(self):
        """'ok' can be a prior-message ack; never approves a stale tool."""
        assert is_approval("ok", has_pending_tool=False) is False

    def test_k_with_no_pending_returns_false(self):
        assert is_approval("k", has_pending_tool=False) is False


class TestIsApprovalNotApprovalPhrases:
    def test_unknown_phrase_rejected(self):
        assert is_approval("maybe later", has_pending_tool=True) is False

    def test_empty_string_rejected(self):
        assert is_approval("", has_pending_tool=True) is False

    def test_long_message_rejected(self):
        assert (
            is_approval(
                "Actually, I think we should hold off for now",
                has_pending_tool=True,
            )
            is False
        )
