from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cosinabox.jobs.extraction import (
    EXTRACTION_PROMPT,
    is_source_processed,
    mark_source_processed,
    parse_extraction_response,
)
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestIdempotency:
    def test_not_processed_initially(self, mem):
        assert is_source_processed(mem, "fireflies", "t1") is False

    def test_mark_and_check(self, mem):
        mark_source_processed(mem, "fireflies", "t1")
        assert is_source_processed(mem, "fireflies", "t1") is True

    def test_different_source_not_affected(self, mem):
        mark_source_processed(mem, "fireflies", "t1")
        assert is_source_processed(mem, "gmail", "t1") is False


class TestParseExtractionResponse:
    def test_valid_json_array(self):
        resp = '[{"text": "Budget approved", "metadata": {"source": "meeting"}}]'
        result = parse_extraction_response(resp)
        assert len(result) == 1
        assert result[0]["text"] == "Budget approved"

    def test_markdown_wrapped_json(self):
        resp = '```json\n[{"text": "fact"}]\n```'
        result = parse_extraction_response(resp)
        assert len(result) == 1

    def test_json_with_preamble(self):
        resp = 'Here are the facts:\n[{"text": "fact"}]'
        result = parse_extraction_response(resp)
        assert len(result) == 1

    def test_malformed_returns_empty(self):
        result = parse_extraction_response("this is not json at all")
        assert result == []

    def test_empty_array(self):
        result = parse_extraction_response("[]")
        assert result == []


class TestExtractionPrompt:
    def test_prompt_contains_json_instruction(self):
        assert "JSON" in EXTRACTION_PROMPT
        assert "ONLY" in EXTRACTION_PROMPT


from cosinabox.jobs.extract_fireflies import ExtractFirefliesJob


class TestExtractFirefliesJob:
    def test_skips_when_fireflies_none(self, mem):
        job = ExtractFirefliesJob(fireflies=None, memory_client=MagicMock(), db=mem, anthropic_client=MagicMock())
        result = job.run()
        assert "skipped" in result.lower()

    def test_skips_already_processed(self, mem):
        mark_source_processed(mem, "fireflies", "t1")
        ff = MagicMock()
        ff.list_recent_meetings.return_value = [{"id": "t1", "title": "Sync", "date": "2026-04-13"}]
        job = ExtractFirefliesJob(fireflies=ff, memory_client=MagicMock(), db=mem, anthropic_client=MagicMock())
        result = job.run()
        assert "0 facts" in result or "skipped" in result.lower()

    def test_extracts_from_transcript(self, mem):
        ff = MagicMock()
        ff.list_recent_meetings.return_value = [{"id": "t1", "title": "Strategy", "date": "2026-04-13"}]
        ff.get_transcript.return_value = {
            "id": "t1", "title": "Strategy",
            "sentences": [{"text": "We decided to launch in Q3", "speaker_name": "Alice"}] * 5,
            "duration": 600,
        }

        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = '[{"text": "Decision: launch in Q3", "metadata": {"source": "meeting"}}]'
        mock_response.content = [text_block]
        anthropic = MagicMock()
        anthropic.messages.create.return_value = mock_response

        mc = MagicMock()
        job = ExtractFirefliesJob(fireflies=ff, memory_client=mc, db=mem, anthropic_client=anthropic)
        result = job.run()
        mc.store.assert_called_once()
        assert is_source_processed(mem, "fireflies", "t1")


from cosinabox.jobs.extract_gmail import ExtractGmailJob, build_stakeholder_query


class TestBuildStakeholderQuery:
    def test_filters_by_cadence(self):
        stakeholders = [
            {"name": "Alice", "email": "alice@x.com", "cadence": "daily"},
            {"name": "Bob", "email": "bob@x.com", "cadence": "quarterly"},
            {"name": "Carol", "email": "carol@x.com", "cadence": "weekly"},
        ]
        query = build_stakeholder_query(stakeholders)
        assert "alice@x.com" in query
        assert "carol@x.com" in query
        assert "bob@x.com" not in query

    def test_skips_no_email(self):
        stakeholders = [{"name": "NoEmail", "cadence": "daily"}]
        query = build_stakeholder_query(stakeholders)
        assert query == ""

    def test_empty_stakeholders(self):
        assert build_stakeholder_query([]) == ""


class TestExtractGmailJob:
    def test_skips_when_gmail_none(self, mem):
        job = ExtractGmailJob(gmail=None, memory_client=MagicMock(), db=mem, anthropic_client=MagicMock(), stakeholders=[])
        result = job.run()
        assert "skipped" in result.lower()

    def test_skips_when_no_matching_stakeholders(self, mem):
        gmail = MagicMock()
        stakeholders = [{"name": "Bob", "email": "bob@x.com", "cadence": "quarterly"}]
        job = ExtractGmailJob(gmail=gmail, memory_client=MagicMock(), db=mem, anthropic_client=MagicMock(), stakeholders=stakeholders)
        result = job.run()
        assert "0" in result
        gmail.search.assert_not_called()
