"""Tests for conversation memory wiring, summarization trigger, and summary injection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cosinabox import defaults
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Memory summary storage
# ---------------------------------------------------------------------------


class TestMemorySummaries:
    def test_store_and_retrieve_summary(self, mem: Memory) -> None:
        mem.store_summary(
            session_id="s1", summary="Key decisions were made.", messages_summarized=10,
        )
        assert mem.get_latest_summary(session_id="s1") == "Key decisions were made."

    def test_summary_replaces_previous(self, mem: Memory) -> None:
        mem.store_summary(session_id="s1", summary="Old summary", messages_summarized=5)
        mem.store_summary(session_id="s1", summary="New summary", messages_summarized=8)
        assert mem.get_latest_summary(session_id="s1") == "New summary"

    def test_no_summary_returns_none(self, mem: Memory) -> None:
        assert mem.get_latest_summary(session_id="s1") is None

    def test_summary_session_isolation(self, mem: Memory) -> None:
        mem.store_summary(session_id="s1", summary="Session 1", messages_summarized=5)
        mem.store_summary(session_id="s2", summary="Session 2", messages_summarized=5)
        assert mem.get_latest_summary(session_id="s1") == "Session 1"
        assert mem.get_latest_summary(session_id="s2") == "Session 2"


# ---------------------------------------------------------------------------
# Memory message helpers (for summarizer)
# ---------------------------------------------------------------------------


class TestMemoryMessageHelpers:
    def test_message_count(self, mem: Memory) -> None:
        for i in range(5):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")
        assert mem.message_count(session_id="s1") == 5
        assert mem.message_count(session_id="s2") == 0

    def test_oldest_messages(self, mem: Memory) -> None:
        for i in range(10):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")
        oldest = mem.oldest_messages(session_id="s1", count=3)
        assert len(oldest) == 3
        assert oldest[0]["content"] == "msg 0"
        assert oldest[2]["content"] == "msg 2"
        assert "id" in oldest[0]  # needed for deletion

    def test_delete_messages_by_ids(self, mem: Memory) -> None:
        for i in range(5):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")
        oldest = mem.oldest_messages(session_id="s1", count=3)
        ids = [m["id"] for m in oldest]
        deleted = mem.delete_messages_by_ids(ids)
        assert deleted == 3
        assert mem.message_count(session_id="s1") == 2

    def test_delete_empty_ids(self, mem: Memory) -> None:
        assert mem.delete_messages_by_ids([]) == 0


# ---------------------------------------------------------------------------
# Summarization trigger
# ---------------------------------------------------------------------------


class TestSummarizationTrigger:
    def test_below_threshold_no_summarization(self, mem: Memory) -> None:
        from cosinabox.agent.summarize import maybe_summarize

        for i in range(10):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")
        client = MagicMock()
        maybe_summarize(memory=mem, session_id="s1", anthropic_client=client)
        # No API call should be made
        client.messages.create.assert_not_called()

    def test_above_threshold_triggers_summarization(self, mem: Memory) -> None:
        from cosinabox.agent.summarize import maybe_summarize

        # Fill beyond threshold
        for i in range(defaults.CONVERSATION_SUMMARIZE_THRESHOLD + 5):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")

        # Mock the Sonnet API call
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Summary: key points discussed."
        mock_response.content = [text_block]
        client = MagicMock()
        client.messages.create.return_value = mock_response

        maybe_summarize(memory=mem, session_id="s1", anthropic_client=client)

        # API should have been called
        client.messages.create.assert_called_once()
        # Summary should be stored
        assert mem.get_latest_summary(session_id="s1") is not None
        # Old messages should be deleted, keeping only KEEP_RECENT
        remaining = mem.message_count(session_id="s1")
        assert remaining == defaults.CONVERSATION_SUMMARIZE_KEEP_RECENT

    def test_summarization_api_failure_is_graceful(self, mem: Memory) -> None:
        from cosinabox.agent.summarize import maybe_summarize

        for i in range(defaults.CONVERSATION_SUMMARIZE_THRESHOLD + 5):
            mem.store_message(role="user", content=f"msg {i}", session_id="s1")

        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API down")

        original_count = mem.message_count(session_id="s1")
        maybe_summarize(memory=mem, session_id="s1", anthropic_client=client)
        # Messages should NOT be deleted on failure
        assert mem.message_count(session_id="s1") == original_count
        assert mem.get_latest_summary(session_id="s1") is None


# ---------------------------------------------------------------------------
# AgentLoop memory integration
# ---------------------------------------------------------------------------


class TestAgentLoopMemoryIntegration:
    def test_loop_stores_user_and_assistant_messages(self, mem: Memory) -> None:
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello! How can I help?"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            memory=mem,
            system_prompt="You are a test.",
        )

        loop.run(prompt="Hi there", session_id="test-session")

        # Both user and assistant messages should be stored
        messages = mem.recent_messages(session_id="test-session", limit=10)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hi there"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hello! How can I help?"

    def test_loop_loads_history_from_memory(self, mem: Memory) -> None:
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        # Pre-populate history
        mem.store_message(role="user", content="What's the weather?", session_id="s1")
        mem.store_message(role="assistant", content="It's sunny.", session_id="s1")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 100
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Sure, it's still sunny!"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            memory=mem,
            system_prompt="You are a test.",
        )

        loop.run(prompt="Is it still sunny?", session_id="s1")

        # Verify the API call included history
        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Should be: [history user, history assistant, new user]
        assert len(messages) == 3
        assert messages[0]["content"] == "What's the weather?"
        assert messages[1]["content"] == "It's sunny."
        assert messages[2]["content"] == "Is it still sunny?"

    def test_loop_injects_summary_into_system_prompt(self, mem: Memory) -> None:
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mem.store_summary(
            session_id="s1",
            summary="Previously discussed: project timeline.",
            messages_summarized=10,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 100
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Yes!"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            memory=mem,
            system_prompt="You are a CoS.",
        )

        loop.run(prompt="Continue", session_id="s1")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_blocks = call_kwargs["system"]
        system_text = system_blocks[0]["text"]
        assert "project timeline" in system_text
        assert "PREVIOUS CONVERSATION CONTEXT" in system_text

    def test_loop_without_memory_works_unchanged(self) -> None:
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            system_prompt="You are a test.",
        )

        result = loop.run(prompt="hi", session_id="test")
        assert result.final_text == "Hello!"
