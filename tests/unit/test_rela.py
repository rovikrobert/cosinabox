from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.agent.rela import RELA_SYSTEM_PROMPT, create_rela_agent
from cosinabox.tools.rela_tool import rela_query_handler


class TestRelaPrompt:
    def test_prompt_mentions_scoring(self):
        assert "recency" in RELA_SYSTEM_PROMPT.lower()
        assert "meeting frequency" in RELA_SYSTEM_PROMPT.lower()

    def test_prompt_enforces_read_only(self):
        assert "READ-ONLY" in RELA_SYSTEM_PROMPT


class TestCreateRelaAgent:
    def test_creates_subagent_with_rela_namespace(self):
        agent = create_rela_agent(agent_loop=MagicMock(), memory_client=MagicMock())
        assert agent.name == "rela"
        assert agent.namespace == "rela"


class TestRelaQueryHandler:
    def test_returns_response(self):
        mock_agent = MagicMock()
        mock_agent.query.return_value = "Alice: health 75, warming trend"
        handler = rela_query_handler(mock_agent)
        result = handler(query="How's Alice?")
        assert "75" in result

    def test_handles_missing_agent(self):
        handler = rela_query_handler(None)
        result = handler(query="test")
        assert "not configured" in result.lower()

    def test_handles_error(self):
        mock_agent = MagicMock()
        mock_agent.query.side_effect = RuntimeError("timeout")
        handler = rela_query_handler(mock_agent)
        result = handler(query="test")
        assert "failed" in result.lower()
