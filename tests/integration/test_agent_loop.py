"""Integration test: AgentLoop against a deterministic recorded transcript."""

from __future__ import annotations

from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router


class _StubResponseClient:
    """Returns canned Anthropic responses in order."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.messages = self  # duck-type

    def create(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0)


def test_loop_aborts_when_cost_tracker_blocks(monkeypatch) -> None:
    monkeypatch.setattr("cosinabox.agent.loop.time.sleep", lambda *_: None)
    cost = CostTracker(per_message_cap_usd=0.01, daily_cap_usd=0.01)
    cost.record(0.01)  # exhaust daily cap

    class _BoomClient:
        # `messages = None` in the spec is a placeholder comment style;
        # duck-typing requires messages.create to be callable, so we
        # self-reference like _StubResponseClient does.
        def __init__(self):
            self.messages = self

        def create(self, **_):
            from cosinabox.agent.cost import CostExceeded

            raise CostExceeded("daily")

    loop = AgentLoop(
        anthropic_client=_BoomClient(),  # type: ignore[arg-type]
        router=Router(),
        cost_tracker=cost,
        tools={},
    )
    result = loop.run(prompt="hi", session_id="s1")
    assert result.stopped_reason == "cost_exceeded"
