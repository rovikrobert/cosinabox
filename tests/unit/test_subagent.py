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

    def test_allowed_tools_passed_to_loop(self):
        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(final_text="ok")
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=mock_loop, memory_client=MagicMock(),
            allowed_tools=[],
        )
        agent.query("any")
        assert mock_loop.run.call_args.kwargs.get("allowed_tools") == []

    def test_allowed_tools_default_is_empty_list(self):
        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(final_text="ok")
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=mock_loop, memory_client=MagicMock(),
        )
        agent.query("any")
        assert mock_loop.run.call_args.kwargs.get("allowed_tools") == []

    def test_ingest_concurrency_bounded_by_semaphore(self):
        """Peak concurrent ingests must not exceed the configured bound."""
        import threading

        bound = 3
        peak = {"n": 0}
        current = {"n": 0}
        lock = threading.Lock()
        started = threading.Event()
        finish = threading.Event()

        def fake_run(**kwargs):
            with lock:
                current["n"] += 1
                if current["n"] > peak["n"]:
                    peak["n"] = current["n"]
            started.set()
            finish.wait(timeout=5)
            with lock:
                current["n"] -= 1
            return MagicMock(final_text="ok")

        mock_loop = MagicMock()
        mock_loop.run.side_effect = fake_run

        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=mock_loop, memory_client=MagicMock(),
            max_concurrent_ingests=bound,
        )
        threads = []
        # Fire 10 ingests; peak must stay ≤ bound because the semaphore blocks
        # the 4th-10th workers until the first few release.
        for _ in range(10):
            agent.ingest("content")
        # Let things settle, then release workers to finish
        import time
        # Give threads time to start up to the semaphore limit
        for _ in range(50):
            if current["n"] >= bound:
                break
            time.sleep(0.02)
        # Peak observed should be exactly bound (semaphore blocks extras)
        time.sleep(0.1)
        assert peak["n"] <= bound, f"peak concurrency {peak['n']} exceeded bound {bound}"
        finish.set()
        # Drain
        time.sleep(0.3)

    def test_query_session_id_uses_full_uuid_hex(self):
        """Plan 4 polish item 8: session ids use full hex (32 chars) not [:8].
        [:8] has a birthday-collision risk for long-running agents."""
        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(final_text="ok")
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=mock_loop, memory_client=MagicMock(),
        )
        agent.query("q")
        sid = mock_loop.run.call_args.kwargs["session_id"]
        prefix = "rela-query-"
        assert sid.startswith(prefix)
        hex_part = sid[len(prefix):]
        assert len(hex_part) == 32, f"Expected full uuid hex (32 chars), got {hex_part!r}"

    def test_query_session_ids_are_unique(self):
        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(final_text="ok")
        agent = SubAgent(
            name="rela", namespace="rela", system_prompt="test",
            agent_loop=mock_loop, memory_client=MagicMock(),
        )
        agent.query("q1")
        agent.query("q2")
        sid1 = mock_loop.run.call_args_list[0].kwargs["session_id"]
        sid2 = mock_loop.run.call_args_list[1].kwargs["session_id"]
        assert sid1 != sid2
        assert sid1.startswith("rela-query-")
        assert sid2.startswith("rela-query-")
