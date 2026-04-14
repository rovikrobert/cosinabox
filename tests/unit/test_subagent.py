from __future__ import annotations

import time
from unittest.mock import MagicMock

from cosinabox.agent.subagent import SubAgent


class TestSubAgent:
    def test_query_returns_response(self):
        mock_loop = MagicMock()
        mock_result = MagicMock()
        mock_result.final_text = "Health score: 75"
        mock_loop.run.return_value = mock_result

        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="You are Rela.",
            agent_loop=mock_loop, memory_client=MagicMock(),
        )
        answer = agent.query("How's Alice?")
        assert "75" in answer
        mock_loop.run.assert_called_once()

    def test_ingest_runs_in_background(self):
        mock_loop = MagicMock()
        mock_result = MagicMock()
        mock_result.final_text = "Stored."
        mock_loop.run.return_value = mock_result

        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="You are Rela.",
            agent_loop=mock_loop, memory_client=MagicMock(),
        )
        agent.ingest("Meeting context: Alice was engaged")
        time.sleep(0.2)
        mock_loop.run.assert_called_once()

    def test_namespace_forced_on_memory_store(self):
        mc = MagicMock()
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="You are Rela.",
            agent_loop=MagicMock(), memory_client=mc,
        )
        agent._namespaced_client.store(text="fact", metadata={}, namespace="wrong")
        mc.store.assert_called_once()
        call_kwargs = mc.store.call_args.kwargs
        assert call_kwargs["namespace"] == "rela"

    def test_namespace_forced_on_recall(self):
        mc = MagicMock()
        mc.recall.return_value = []
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=MagicMock(), memory_client=mc,
        )
        agent._namespaced_client.recall(query="test", namespace="wrong")
        mc.recall.assert_called_once()
        assert mc.recall.call_args.kwargs["namespace"] == "rela"
