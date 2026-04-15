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


class TestExtractionPartialFailure:
    """When store() raises mid-loop, the source must NOT be marked processed —
    otherwise next run skips it and the un-stored facts are lost forever."""

    def _build_response(self, facts_json: str) -> MagicMock:
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = facts_json
        mock_response.content = [text_block]
        return mock_response

    def test_fireflies_not_marked_processed_when_store_raises(self, mem):
        from cosinabox.memory.client import MemoryServiceError

        ff = MagicMock()
        ff.list_recent_meetings.return_value = [{"id": "t1", "title": "Strategy"}]
        ff.get_transcript.return_value = {
            "id": "t1", "title": "Strategy",
            "sentences": [{"text": "Decision one", "speaker_name": "A"}] * 5,
            "duration": 600,
        }

        facts_json = (
            '[{"text": "fact1", "metadata": {}},'
            ' {"text": "fact2", "metadata": {}},'
            ' {"text": "fact3", "metadata": {}}]'
        )
        anthropic = MagicMock()
        anthropic.messages.create.return_value = self._build_response(facts_json)

        mc = MagicMock()
        # store succeeds for fact1, raises for fact2 (fact3 never attempted)
        mc.store.side_effect = ["id1", MemoryServiceError("503"), "id3"]

        job = ExtractFirefliesJob(
            fireflies=ff, memory_client=mc, db=mem, anthropic_client=anthropic,
        )
        job.run()

        # fact1 stored, loop aborted at fact2 => 2 calls total
        assert mc.store.call_count == 2
        # Source NOT marked processed — re-run will retry
        assert is_source_processed(mem, "fireflies", "t1") is False

    def test_fireflies_marked_processed_when_all_stores_succeed(self, mem):
        ff = MagicMock()
        ff.list_recent_meetings.return_value = [{"id": "t2", "title": "Sync"}]
        ff.get_transcript.return_value = {
            "id": "t2", "title": "Sync",
            "sentences": [{"text": "Decision", "speaker_name": "A"}] * 5,
            "duration": 600,
        }
        facts_json = (
            '[{"text": "f1", "metadata": {}},'
            ' {"text": "f2", "metadata": {}},'
            ' {"text": "f3", "metadata": {}}]'
        )
        anthropic = MagicMock()
        anthropic.messages.create.return_value = self._build_response(facts_json)
        mc = MagicMock()

        job = ExtractFirefliesJob(
            fireflies=ff, memory_client=mc, db=mem, anthropic_client=anthropic,
        )
        job.run()

        assert mc.store.call_count == 3
        assert is_source_processed(mem, "fireflies", "t2") is True

    def test_gmail_not_marked_processed_when_store_raises(self, mem):
        from cosinabox.memory.client import MemoryServiceError

        gmail = MagicMock()
        msg = MagicMock()
        msg.id = "m1"
        msg.sender = "alice@x.com"
        msg.subject = "Plan"
        msg.snippet = "Body"
        gmail.search.return_value = [msg]

        facts_json = (
            '[{"text": "f1", "metadata": {}},'
            ' {"text": "f2", "metadata": {}},'
            ' {"text": "f3", "metadata": {}}]'
        )
        anthropic = MagicMock()
        anthropic.messages.create.return_value = self._build_response(facts_json)

        mc = MagicMock()
        mc.store.side_effect = ["id1", MemoryServiceError("503"), "id3"]

        stakeholders = [{"name": "Alice", "email": "alice@x.com", "cadence": "daily"}]
        job = ExtractGmailJob(
            gmail=gmail, memory_client=mc, db=mem,
            anthropic_client=anthropic, stakeholders=stakeholders,
        )
        job.run()

        assert mc.store.call_count == 2
        assert is_source_processed(mem, "gmail", "m1") is False

    def test_gmail_marked_processed_when_all_stores_succeed(self, mem):
        gmail = MagicMock()
        msg = MagicMock()
        msg.id = "m2"
        msg.sender = "alice@x.com"
        msg.subject = "Plan"
        msg.snippet = "Body"
        gmail.search.return_value = [msg]
        facts_json = (
            '[{"text": "f1", "metadata": {}},'
            ' {"text": "f2", "metadata": {}},'
            ' {"text": "f3", "metadata": {}}]'
        )
        anthropic = MagicMock()
        anthropic.messages.create.return_value = self._build_response(facts_json)
        mc = MagicMock()

        stakeholders = [{"name": "Alice", "email": "alice@x.com", "cadence": "daily"}]
        job = ExtractGmailJob(
            gmail=gmail, memory_client=mc, db=mem,
            anthropic_client=anthropic, stakeholders=stakeholders,
        )
        job.run()

        assert mc.store.call_count == 3
        assert is_source_processed(mem, "gmail", "m2") is True
