from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.agent.summarization import maybe_summarize


def test_no_summarize_below_threshold() -> None:
    msgs = [{"role": "user", "content": str(i)} for i in range(10)]
    client = MagicMock()
    out = maybe_summarize(msgs, client=client, threshold=25)
    assert out == msgs
    client.messages.create.assert_not_called()


def test_summarize_above_threshold_collapses_old() -> None:
    msgs = [{"role": "user", "content": str(i)} for i in range(30)]
    client = MagicMock()
    fake = MagicMock()
    fake.content = [MagicMock(type="text", text="Summary of older messages.")]
    client.messages.create.return_value = fake
    out = maybe_summarize(msgs, client=client, threshold=25, keep_recent=10)
    assert len(out) == 11  # 1 summary + 10 recent
    assert "Summary of older messages." in out[0]["content"]
