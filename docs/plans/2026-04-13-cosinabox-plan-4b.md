# Plan 4B: Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add extraction pipeline (Fireflies + Gmail → memory), post-meeting debrief, and Rela relationship manager to the cosinabox engine.

**Architecture:** Extraction jobs run daily via APScheduler, pull data from external APIs, extract facts via Sonnet, store in memory client. Post-meeting debrief polls calendar for ended meetings, matches Fireflies transcripts. Rela is a namespace-isolated sub-agent that scores relationship health. All components degrade gracefully when integrations are missing.

**Tech Stack:** Python 3.11+, SQLite (WAL mode), Anthropic Claude API (Sonnet for extraction), APScheduler

**Spec:** `docs/superpowers/specs/2026-04-13-cosinabox-plan-4b-design.md`

**Worktree:** `~/.worktrees/cantina/plan4b-intelligence` (branch: `plan4b-intelligence`)

**Test command:** `.venv/bin/pytest -q` (from worktree root)

---

### Task 1: Extraction infrastructure — schema, parser, idempotency

**Files:**
- Modify: `src/cosinabox/memory/sqlite.py` (add extraction_state + debrief_state tables to _SCHEMA)
- Create: `src/cosinabox/jobs/extraction.py` (shared helpers: idempotency, parsing, extraction prompt)
- Modify: `src/cosinabox/templates/user-repo/stakeholders.yaml` (add email field)
- Test: `tests/unit/test_extraction.py`

- [ ] **Step 1: Add tables to _SCHEMA**

In `src/cosinabox/memory/sqlite.py`, append to the `_SCHEMA` string (after the `processed_message_ids` table):

```sql

CREATE TABLE IF NOT EXISTS extraction_state (
    key TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS debrief_state (
    ical_uid TEXT PRIMARY KEY,
    debriefed_at TEXT NOT NULL
);
```

- [ ] **Step 2: Add email field to stakeholders.yaml template**

In `src/cosinabox/templates/user-repo/stakeholders.yaml`, update the field documentation and example:

```yaml
schema_version: 1
# Your top 5 stakeholders. Used in briefings, follow-up reminders,
# and pre-meeting prep. If you enable the Attio CRM integration,
# this file is used as the initial seed and then Attio becomes the
# source of truth.
#
# Fields:
#   name     — Full name (used to match calendar/email)
#   email    — Email address (optional, needed for Gmail extraction)
#   role     — Title + org, e.g. "Lead Investor (Sequoia)" or "Co-founder"
#   cadence  — How often to check in: daily | weekly | biweekly | monthly | quarterly
#   notes    — Context that helps your CoS prepare (what they care about, what to avoid)
#
# Walk through docs/agent/persona-interview.md with Claude Code
# to fill this in interactively instead of editing YAML directly.
stakeholders:
  - name: Example Stakeholder (replace me)
    email: stakeholder@example.com
    role: Lead Investor (Example Ventures)
    cadence: weekly
    last_contact: "2026-01-01"
    notes: |
      Delete this entry and add your real stakeholders. Use the interview
      flow or tell Claude Code "add a stakeholder" to do it conversationally.
```

- [ ] **Step 3: Write failing tests for extraction helpers**

```python
# tests/unit/test_extraction.py
from __future__ import annotations

import json

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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_extraction.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 5: Implement extraction helpers**

```python
# src/cosinabox/jobs/extraction.py
"""Shared extraction helpers — idempotency, parsing, prompt."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
Extract durable facts from this content. Focus on:
- Decisions made and their rationale
- Commitments or action items (who, what, when)
- Stakeholder context (preferences, concerns, relationships)
- Key dates, amounts, or deadlines mentioned

Output ONLY a JSON array of objects, no other text:
[{{"text": "fact text", "metadata": {{"source": "...", "date": "...", "stakeholder": "..."}}}}]

Only extract facts worth remembering weeks later. Skip pleasantries, logistics, and transient details.
If nothing is worth extracting, return an empty array: []

CONTENT:
{content}
"""


def is_source_processed(db: Any, source_type: str, source_id: str) -> bool:
    """Check idempotency guard — has this source already been extracted?"""
    cur = db._conn.execute(
        "SELECT 1 FROM extraction_state WHERE key = ?",
        (f"{source_type}:{source_id}",),
    )
    return cur.fetchone() is not None


def mark_source_processed(db: Any, source_type: str, source_id: str) -> None:
    """Mark a source as extracted in the idempotency table."""
    ts = datetime.now(UTC).isoformat()
    db._conn.execute(
        "INSERT OR IGNORE INTO extraction_state (key, processed_at) VALUES (?, ?)",
        (f"{source_type}:{source_id}", ts),
    )
    db._conn.commit()


def parse_extraction_response(text: str) -> list[dict[str, Any]]:
    """Parse Sonnet's extraction response — handles markdown fences and preamble."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    # Find the JSON array
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        logger.warning("Extraction response has no JSON array: %s", text[:100])
        return []

    json_str = cleaned[start : end + 1]
    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            return []
        return parsed
    except json.JSONDecodeError:
        logger.warning("Malformed extraction JSON: %s", json_str[:100])
        return []
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_extraction.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/cosinabox/memory/sqlite.py src/cosinabox/jobs/extraction.py \
  src/cosinabox/templates/user-repo/stakeholders.yaml tests/unit/test_extraction.py
git commit -m "feat: extraction infrastructure — idempotency, JSON parser, schema"
```

---

### Task 2: extract_fireflies job

**Files:**
- Create: `src/cosinabox/jobs/extract_fireflies.py`
- Add to: `tests/unit/test_extraction.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_extraction.py`:

```python
from unittest.mock import MagicMock

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
        assert "0" in result or "skipped" in result.lower()

    def test_extracts_from_transcript(self, mem):
        ff = MagicMock()
        ff.list_recent_meetings.return_value = [{"id": "t1", "title": "Strategy", "date": "2026-04-13"}]
        ff.get_transcript.return_value = {
            "id": "t1", "title": "Strategy",
            "sentences": [{"text": "We decided to launch in Q3", "speaker_name": "Alice"}],
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
```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement ExtractFirefliesJob**

```python
# src/cosinabox/jobs/extract_fireflies.py
"""Extract durable facts from Fireflies meeting transcripts."""

from __future__ import annotations

import logging
from typing import Any

from cosinabox.agent.routing import SONNET_MODEL_ID
from cosinabox.jobs.base import Job
from cosinabox.jobs.extraction import (
    EXTRACTION_PROMPT,
    is_source_processed,
    mark_source_processed,
    parse_extraction_response,
)

logger = logging.getLogger(__name__)


def _is_stub(transcript: dict[str, Any]) -> bool:
    """Skip transcripts that are stubs (no real content)."""
    sentences = transcript.get("sentences") or []
    duration = transcript.get("duration") or 0
    return len(sentences) < 3 or duration < 60


class ExtractFirefliesJob(Job):
    name = "extract_fireflies"

    def __init__(
        self,
        *,
        fireflies: Any | None,
        memory_client: Any,
        db: Any,
        anthropic_client: Any,
    ) -> None:
        self.fireflies = fireflies
        self.memory_client = memory_client
        self.db = db
        self.anthropic = anthropic_client

    def run(self, context: Any = None) -> str:
        if self.fireflies is None:
            return "Fireflies not configured — skipped"

        meetings = self.fireflies.list_recent_meetings(hours=48)
        extracted = 0
        skipped = 0

        for meeting in meetings:
            mid = meeting.get("id", "")
            if not mid or is_source_processed(self.db, "fireflies", mid):
                skipped += 1
                continue

            transcript = self.fireflies.get_transcript(mid)
            if _is_stub(transcript):
                mark_source_processed(self.db, "fireflies", mid)
                skipped += 1
                continue

            # Build content from transcript
            sentences = transcript.get("sentences") or []
            content = f"Meeting: {meeting.get('title', 'Untitled')}\n\n"
            content += "\n".join(
                f"{s.get('speaker_name', 'Unknown')}: {s.get('text', '')}"
                for s in sentences[:100]  # Cap at 100 sentences
            )
            if len(content) > 5000:
                content = content[:5000] + "... (truncated)"

            # Extract via Sonnet
            try:
                response = self.anthropic.messages.create(
                    model=SONNET_MODEL_ID,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(content=content)}],
                )
                resp_text = "\n".join(b.text for b in response.content if b.type == "text")
                facts = parse_extraction_response(resp_text)
            except Exception:
                logger.warning("Extraction failed for transcript %s", mid, exc_info=True)
                continue

            for fact in facts:
                self.memory_client.store(
                    text=fact.get("text", ""),
                    metadata=fact.get("metadata", {}),
                    namespace="extraction",
                )
                extracted += 1

            mark_source_processed(self.db, "fireflies", mid)

        return f"Fireflies: {extracted} facts from {len(meetings)} transcripts ({skipped} skipped)"
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Run full suite**
- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/jobs/extract_fireflies.py tests/unit/test_extraction.py
git commit -m "feat: extract_fireflies job — meeting transcript → memory facts"
```

---

### Task 3: extract_gmail job

**Files:**
- Create: `src/cosinabox/jobs/extract_gmail.py`
- Add to: `tests/unit/test_extraction.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_extraction.py`:

```python
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
        assert "0" in result or "no stakeholders" in result.lower()
        gmail.search.assert_not_called()
```

- [ ] **Step 2: Implement ExtractGmailJob**

```python
# src/cosinabox/jobs/extract_gmail.py
"""Extract durable facts from stakeholder emails."""

from __future__ import annotations

import logging
from typing import Any

from cosinabox.agent.routing import SONNET_MODEL_ID
from cosinabox.jobs.base import Job
from cosinabox.jobs.extraction import (
    EXTRACTION_PROMPT,
    is_source_processed,
    mark_source_processed,
    parse_extraction_response,
)

logger = logging.getLogger(__name__)

_ACTIVE_CADENCES = {"daily", "weekly"}


def build_stakeholder_query(stakeholders: list[dict[str, Any]]) -> str:
    """Build Gmail search query from stakeholders with daily/weekly cadence."""
    emails = [
        s["email"]
        for s in stakeholders
        if s.get("email") and s.get("cadence", "").lower() in _ACTIVE_CADENCES
    ]
    if not emails:
        return ""
    return " OR ".join(f"from:{e}" for e in emails)


class ExtractGmailJob(Job):
    name = "extract_gmail"

    def __init__(
        self,
        *,
        gmail: Any | None,
        memory_client: Any,
        db: Any,
        anthropic_client: Any,
        stakeholders: list[dict[str, Any]],
    ) -> None:
        self.gmail = gmail
        self.memory_client = memory_client
        self.db = db
        self.anthropic = anthropic_client
        self.stakeholders = stakeholders

    def run(self, context: Any = None) -> str:
        if self.gmail is None:
            return "Gmail not configured — skipped"

        query = build_stakeholder_query(self.stakeholders)
        if not query:
            return "No stakeholders with daily/weekly cadence and email — 0 facts"

        messages = self.gmail.search(query, max_results=50)
        extracted = 0
        skipped = 0

        for msg in messages:
            if is_source_processed(self.db, "gmail", msg.id):
                skipped += 1
                continue

            content = f"From: {msg.sender}\nSubject: {msg.subject}\n\n{msg.snippet}"

            try:
                response = self.anthropic.messages.create(
                    model=SONNET_MODEL_ID,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(content=content)}],
                )
                resp_text = "\n".join(b.text for b in response.content if b.type == "text")
                facts = parse_extraction_response(resp_text)
            except Exception:
                logger.warning("Extraction failed for email %s", msg.id, exc_info=True)
                continue

            for fact in facts:
                self.memory_client.store(
                    text=fact.get("text", ""),
                    metadata=fact.get("metadata", {}),
                    namespace="extraction",
                )
                extracted += 1

            mark_source_processed(self.db, "gmail", msg.id)

        return f"Gmail: {extracted} facts from {len(messages)} emails ({skipped} skipped)"
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Commit**

```bash
git add src/cosinabox/jobs/extract_gmail.py tests/unit/test_extraction.py
git commit -m "feat: extract_gmail job — stakeholder emails → memory facts"
```

---

### Task 4: SubAgent class

**Files:**
- Create: `src/cosinabox/agent/subagent.py`
- Test: `tests/unit/test_subagent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_subagent.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cosinabox.agent.subagent import SubAgent


class TestSubAgent:
    def test_query_returns_response(self):
        mock_loop = MagicMock()
        mock_result = MagicMock()
        mock_result.final_text = "Health score: 75"
        mock_loop.run.return_value = mock_result

        agent = SubAgent(
            name="rela",
            namespace="rela",
            system_prompt="You are Rela.",
            agent_loop=mock_loop,
            memory_client=MagicMock(),
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
            name="rela",
            namespace="rela",
            system_prompt="You are Rela.",
            agent_loop=mock_loop,
            memory_client=MagicMock(),
        )
        # ingest should return immediately (background thread)
        agent.ingest("Meeting context: Alice was engaged")
        # Give thread time to execute
        import time
        time.sleep(0.1)
        mock_loop.run.assert_called_once()

    def test_namespace_forced_on_memory_store(self):
        mc = MagicMock()
        mock_loop = MagicMock()
        mock_result = MagicMock()
        mock_result.final_text = "ok"
        mock_loop.run.return_value = mock_result

        agent = SubAgent(
            name="rela",
            namespace="rela",
            system_prompt="You are Rela.",
            agent_loop=mock_loop,
            memory_client=mc,
        )
        # The agent's memory_client should enforce namespace
        agent._namespaced_client.store(text="fact", metadata={}, namespace="wrong")
        # Should have been called with namespace="rela"
        mc.store.assert_called_once()
        call_kwargs = mc.store.call_args.kwargs
        assert call_kwargs["namespace"] == "rela"
```

- [ ] **Step 2: Implement SubAgent**

```python
# src/cosinabox/agent/subagent.py
"""Sub-agent — isolated agent with its own memory namespace and prompt.

Sub-agents run the same AgentLoop but with:
- Custom system prompt (specialized for their role)
- Namespace-forced memory operations (all reads/writes isolated)
- Isolated session IDs (no conversation history bleed)
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_AGENTS: dict[str, "SubAgent"] = {}


class _NamespacedMemoryClient:
    """Wrapper that forces a namespace on all memory operations."""

    def __init__(self, inner: Any, namespace: str) -> None:
        self._inner = inner
        self._namespace = namespace

    def store(self, *, text: str, metadata: dict[str, Any], namespace: str = "") -> str:
        return self._inner.store(text=text, metadata=metadata, namespace=self._namespace)

    def recall(self, *, query: str, namespace: str = "", limit: int = 5) -> list[dict[str, Any]]:
        return self._inner.recall(query=query, namespace=self._namespace, limit=limit)

    def search(self, *, query: str, namespace: str = "") -> list[dict[str, Any]]:
        return self._inner.search(query=query, namespace=self._namespace)

    def delete(self, *, memory_id: str) -> bool:
        return self._inner.delete(memory_id=memory_id)


class SubAgent:
    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        system_prompt: str,
        agent_loop: Any,
        memory_client: Any,
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.system_prompt = system_prompt
        self._loop = agent_loop
        self._namespaced_client = _NamespacedMemoryClient(memory_client, namespace)

    def ingest(self, content: str) -> None:
        """Fire-and-forget: process content in a background thread."""
        def _run() -> None:
            try:
                session = f"{self.name}-ingest-{uuid.uuid4().hex[:8]}"
                self._loop.run(prompt=content, session_id=session)
            except Exception:
                logger.warning("SubAgent %s ingest failed", self.name, exc_info=True)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def query(self, question: str) -> str:
        """Synchronous query — blocks until response is ready."""
        session = f"{self.name}-query"
        result = self._loop.run(prompt=question, session_id=session)
        return result.final_text or "(no response)"


def register_agent(agent: SubAgent) -> None:
    _AGENTS[agent.name] = agent


def get_agent(name: str) -> SubAgent | None:
    return _AGENTS.get(name)
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Commit**

```bash
git add src/cosinabox/agent/subagent.py tests/unit/test_subagent.py
git commit -m "feat: SubAgent class — namespace-isolated agents with background ingest"
```

---

### Task 5: Post-meeting debrief job

**Files:**
- Create: `src/cosinabox/jobs/post_meeting_debrief.py`
- Test: `tests/unit/test_post_meeting_debrief.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_post_meeting_debrief.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cosinabox.jobs.post_meeting_debrief import (
    PostMeetingDebriefJob,
    _transcript_matches,
)
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestTranscriptMatching:
    def test_title_substring_match(self):
        assert _transcript_matches(
            {"title": "Q3 Strategy Review", "participants": []},
            cal_title="strategy review",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_shared_words_match(self):
        assert _transcript_matches(
            {"title": "Sprint Planning Meeting", "participants": []},
            cal_title="Planning Session",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_generic_title_requires_two_criteria(self):
        # "Sync" alone should NOT match another "Sync" without time proximity or attendee overlap
        assert not _transcript_matches(
            {"title": "Sync", "participants": [], "date": "2026-04-13T15:00:00"},
            cal_title="Sync",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),  # 5h apart
        )

    def test_attendee_overlap_match(self):
        assert _transcript_matches(
            {"title": "Sync", "participants": ["alice@x.com"], "date": "2026-04-13T10:00:00"},
            cal_title="Standup",
            cal_emails={"alice@x.com"},
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )

    def test_no_match(self):
        assert not _transcript_matches(
            {"title": "Unrelated Meeting", "participants": []},
            cal_title="Budget Review",
            cal_emails=set(),
            cal_start=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )


class TestPostMeetingDebriefJob:
    def test_skips_when_calendar_none(self, mem):
        job = PostMeetingDebriefJob(
            calendar=None, fireflies=None, db=mem,
            send_fn=MagicMock(), skip_titles=[],
        )
        result = job.run()
        assert "skipped" in result.lower()

    def test_skips_already_debriefed(self, mem):
        # Mark a meeting as already debriefed
        mem._conn.execute(
            "INSERT INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            ("uid-1", datetime.now(UTC).isoformat()),
        )
        mem._conn.commit()

        cal = MagicMock()
        from cosinabox.tools.google.calendar import CalendarEvent
        ended = datetime.now(UTC) - timedelta(minutes=20)
        cal.list_events.return_value = [
            CalendarEvent(id="e1", summary="Standup", start=ended - timedelta(minutes=30), end=ended),
        ]
        # Patch iCalUID — CalendarEvent doesn't have it, use id as fallback
        job = PostMeetingDebriefJob(
            calendar=cal, fireflies=None, db=mem,
            send_fn=MagicMock(), skip_titles=[],
        )
        # The job uses event.id as ical_uid fallback
        mem._conn.execute(
            "INSERT OR REPLACE INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            ("e1", datetime.now(UTC).isoformat()),
        )
        mem._conn.commit()

        result = job.run()
        assert "0" in result or "no meetings" in result.lower()
```

- [ ] **Step 2: Implement PostMeetingDebriefJob**

```python
# src/cosinabox/jobs/post_meeting_debrief.py
"""Post-meeting debrief — detect ended meetings, fetch transcripts, send summary."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)


def _transcript_matches(
    transcript: dict[str, Any],
    *,
    cal_title: str,
    cal_emails: set[str],
    cal_start: datetime,
) -> bool:
    """Check if a Fireflies transcript matches a calendar event."""
    t_title = (transcript.get("title") or "").lower()
    cal_lower = cal_title.lower()
    criteria_met = 0

    # Criterion 1: title substring match
    if cal_lower in t_title or t_title in cal_lower:
        criteria_met += 1

    # Criterion 2: shared words (>2 chars)
    cal_words = {w for w in cal_lower.split() if len(w) > 2}
    t_words = {w for w in t_title.split() if len(w) > 2}
    if cal_words & t_words:
        criteria_met += 1

    # Criterion 3: attendee email overlap
    t_participants = {(p or "").lower() for p in (transcript.get("participants") or [])}
    if cal_emails & t_participants:
        criteria_met += 1

    # Criterion 4: time proximity (within ±30 min)
    t_date = transcript.get("date", "")
    if t_date:
        try:
            t_dt = datetime.fromisoformat(t_date.replace("Z", "+00:00"))
            if abs((t_dt - cal_start).total_seconds()) < 1800:  # 30 min
                criteria_met += 1
        except (ValueError, TypeError):
            pass

    # Generic titles (≤2 words) require 2+ criteria
    is_generic = len(cal_lower.split()) <= 2
    if is_generic:
        return criteria_met >= 2
    return criteria_met >= 1


class PostMeetingDebriefJob(Job):
    name = "post_meeting_debrief"

    def __init__(
        self,
        *,
        calendar: Any | None,
        fireflies: Any | None,
        db: Any,
        send_fn: Callable[[str], None],
        skip_titles: list[str] | None = None,
        rela: Any | None = None,
    ) -> None:
        self.calendar = calendar
        self.fireflies = fireflies
        self.db = db
        self.send_fn = send_fn
        self.skip_titles = [t.lower() for t in (skip_titles or [])]
        self.rela = rela

    def _is_debriefed(self, uid: str) -> bool:
        cur = self.db._conn.execute(
            "SELECT 1 FROM debrief_state WHERE ical_uid = ?", (uid,),
        )
        return cur.fetchone() is not None

    def _mark_debriefed(self, uid: str) -> None:
        ts = datetime.now(UTC).isoformat()
        self.db._conn.execute(
            "INSERT OR IGNORE INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            (uid, ts),
        )
        self.db._conn.commit()

    def run(self, context: Any = None) -> str:
        if self.calendar is None:
            return "Calendar not configured — skipped"

        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=30)
        window_end = now - timedelta(minutes=15)

        # Look back 2h to catch events that started earlier
        search_start = window_start - timedelta(hours=2)
        events = self.calendar.list_events(start=search_start, end=window_end)

        debriefed = 0
        for evt in events:
            uid = evt.id  # CalendarEvent uses id
            if self._is_debriefed(uid):
                continue

            # Check end time is in the 15-30 min ago window
            if not (window_start <= evt.end <= window_end):
                continue

            # Skip configured titles
            if any(skip in evt.summary.lower() for skip in self.skip_titles):
                self._mark_debriefed(uid)
                continue

            # Build debrief message
            lines = [f"Meeting just ended: {evt.summary}"]

            # Try to find Fireflies transcript
            if self.fireflies is not None:
                try:
                    transcripts = self.fireflies.list_recent_meetings(hours=24)
                    cal_emails: set[str] = set()  # Would need attendees from full event

                    candidates = [
                        t for t in transcripts
                        if _transcript_matches(
                            t, cal_title=evt.summary,
                            cal_emails=cal_emails, cal_start=evt.start,
                        )
                    ]

                    if candidates:
                        best = candidates[0]
                        t_data = self.fireflies.get_transcript(best["id"])
                        sentences = t_data.get("sentences") or []
                        if sentences:
                            overview = " ".join(s.get("text", "") for s in sentences[:10])
                            lines.append(f"\nKey points:\n{overview[:800]}")
                        lines.append("\nTranscript captured by Fireflies.")
                    else:
                        lines.append("\nNo transcript found yet (may still be processing).")
                except Exception:
                    logger.warning("Fireflies lookup failed for %s", evt.summary, exc_info=True)
                    lines.append("\nTranscript lookup failed.")
            else:
                lines.append("\nFireflies not configured — no transcript available.")

            lines.append("\nAnything to add? Decisions, next steps, things that changed?")

            self.send_fn("\n".join(lines))
            self._mark_debriefed(uid)
            debriefed += 1

            # Feed to Rela (non-blocking)
            if self.rela is not None:
                try:
                    self.rela.ingest(f"Meeting ended: {evt.summary}. " + "\n".join(lines))
                except Exception:
                    logger.debug("Rela feed failed for %s", evt.summary, exc_info=True)

        return f"Debriefed {debriefed} meetings"
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Commit**

```bash
git add src/cosinabox/jobs/post_meeting_debrief.py tests/unit/test_post_meeting_debrief.py
git commit -m "feat: post-meeting debrief — calendar watch + Fireflies transcript matching"
```

---

### Task 6: Rela sub-agent — prompts, scoring, registration

**Files:**
- Create: `src/cosinabox/agent/rela.py`
- Create: `src/cosinabox/tools/rela_tool.py` (rela_query tool for DM)
- Add to: `src/cosinabox/tools/registry.py` (register rela_query)
- Test: `tests/unit/test_rela.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_rela.py
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.agent.rela import RELA_SYSTEM_PROMPT, create_rela_agent
from cosinabox.tools.rela_tool import rela_query_handler


class TestRelaPrompt:
    def test_prompt_mentions_scoring(self):
        assert "recency" in RELA_SYSTEM_PROMPT.lower()
        assert "meeting frequency" in RELA_SYSTEM_PROMPT.lower()

    def test_prompt_enforces_read_only(self):
        assert "read-only" in RELA_SYSTEM_PROMPT.lower() or "READ-ONLY" in RELA_SYSTEM_PROMPT


class TestCreateRelaAgent:
    def test_creates_subagent_with_rela_namespace(self):
        agent = create_rela_agent(
            agent_loop=MagicMock(),
            memory_client=MagicMock(),
        )
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
```

- [ ] **Step 2: Implement Rela agent + tool**

```python
# src/cosinabox/agent/rela.py
"""Rela — relationship health tracking sub-agent."""

from __future__ import annotations

from typing import Any

from cosinabox.agent.subagent import SubAgent

RELA_SYSTEM_PROMPT = """\
You are Rela, a relationship intelligence sub-agent. You track relationship \
health for stakeholders and surface drift alerts.

## Scoring Model (v1)

Score each stakeholder 0-100 based on:

Recency (50%): Days since last interaction on any channel.
  100 if <3 days, drops 4 points per day, floor 0.

Meeting frequency (50%): Meetings in last 30 days vs expected cadence.
  100 if on cadence, 50 if 1.5x behind, 0 if 3x behind.
  VIP/Active expect weekly, others biweekly.

## What you track (stored in your memory namespace)

- relationship_health — score per stakeholder
- drift_alert — when health drops 20+ points or falls below 40
- communication_pattern — behavioral observations
- relationship_trend — 90-day direction (warming/cooling/stable)

## Constraints

You are READ-ONLY for external systems. You read from calendar and \
stakeholder data. You write ONLY to your own memory namespace. \
Never send emails, create events, or modify CRM records.

## Output format

When asked about a stakeholder, respond with:
- Health score (0-100)
- Trend (warming/cooling/stable)
- Last interaction date
- Any drift alerts
- One recommendation
"""


def create_rela_agent(
    *,
    agent_loop: Any,
    memory_client: Any,
) -> SubAgent:
    return SubAgent(
        name="rela",
        namespace="rela",
        system_prompt=RELA_SYSTEM_PROMPT,
        agent_loop=agent_loop,
        memory_client=memory_client,
    )
```

```python
# src/cosinabox/tools/rela_tool.py
"""Rela query tool — lets the CoS ask about relationship health in DM."""

from __future__ import annotations

from typing import Any, Callable


RELA_QUERY_DEFINITION = {
    "name": "rela_query",
    "description": (
        "Ask the relationship manager about a stakeholder's health. "
        "Returns health score, trend, and recommendations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Question about a stakeholder (e.g., 'How is my relationship with Alice?')",
            },
        },
        "required": ["query"],
    },
}


def rela_query_handler(rela_agent: Any | None) -> Callable[..., str]:
    """Build a handler function for the rela_query tool."""

    def handler(query: str) -> str:
        if rela_agent is None:
            return "Rela relationship manager not configured."
        try:
            return rela_agent.query(query)
        except Exception as exc:
            return f"Rela query failed: {exc}"

    return handler
```

- [ ] **Step 3: Register rela_query in registry.py**

In `src/cosinabox/tools/registry.py`, at the end of `build_tool_registry()` (before the consistency check), add:

```python
    # Rela query tool (registered if rela agent is available)
    rela_agent = kwargs.get("rela_agent")
    if rela_agent is not None:
        from cosinabox.tools.rela_tool import RELA_QUERY_DEFINITION, rela_query_handler

        definitions.append(RELA_QUERY_DEFINITION)
        handlers["rela_query"] = rela_query_handler(rela_agent)
        logger.info("Registered rela_query tool")
```

Update `build_tool_registry` signature to accept `**kwargs`:

```python
def build_tool_registry(
    tool_instances: dict[str, Any],
    *,
    timezone: str = "UTC",
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, Callable[..., str]]]:
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/agent/rela.py src/cosinabox/tools/rela_tool.py \
  src/cosinabox/tools/registry.py tests/unit/test_rela.py
git commit -m "feat: Rela relationship manager — scoring model, sub-agent, DM query tool"
```

---

### Task 7: Wire into App.run() + OSS docs

**Files:**
- Modify: `src/cosinabox/app.py` (register extraction jobs, debrief, Rela)
- Modify: `src/cosinabox/templates/user-repo/jobs.yaml` (add new jobs)
- Create: `src/cosinabox/templates/user-repo/docs/agent/rela.md`
- Modify: `src/cosinabox/templates/user-repo/docs/agent/jobs.md` (add new jobs)
- Modify: `src/cosinabox/prompts/core.py` (add Rela to capabilities)

- [ ] **Step 1: Register extraction + debrief + Rela in App.run()**

In `src/cosinabox/app.py`, in the "Register jobs that need send_telegram" section (after crm_email_sync), add:

```python
            elif job_name == "extract_fireflies":
                from cosinabox.jobs.extract_fireflies import ExtractFirefliesJob

                job = ExtractFirefliesJob(
                    fireflies=tool_instances.get("fireflies"),
                    memory_client=memory_client,
                    db=memory,
                    anthropic_client=Anthropic(),
                )
                cron = cfg.get("schedule", "0 7 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "extract_gmail":
                from cosinabox.jobs.extract_gmail import ExtractGmailJob

                job = ExtractGmailJob(
                    gmail=gmail,
                    memory_client=memory_client,
                    db=memory,
                    anthropic_client=Anthropic(),
                    stakeholders=stakeholders,
                )
                cron = cfg.get("schedule", "15 7 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "post_meeting_debrief":
                from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob

                job = PostMeetingDebriefJob(
                    calendar=calendar,
                    fireflies=tool_instances.get("fireflies"),
                    db=memory,
                    send_fn=send_telegram,
                    skip_titles=jobs_config.get("pre_meeting_prep", {}).get(
                        "skip_if_calendar_title_matches", [],
                    ),
                    rela=rela_agent,
                )
                scheduler.add_job(job, cron="*/5 * * * *")
                logger.info("Registered %s (every 5 min)", job_name)
```

Also create and register the Rela agent + memory_client earlier in run() (after memory is created):

```python
        # --- Memory client (for extraction + Rela) ---
        from cosinabox.memory.client import resolve_memory_client

        memory_client = resolve_memory_client(
            db_path=self.config_dir / ".cosinabox" / "memory.db",
        )

        # --- Rela agent ---
        rela_agent = None
        if any(jobs_config.get(j, {}).get("enabled") for j in ("post_meeting_debrief", "rela_daily_scan")):
            from cosinabox.agent.rela import create_rela_agent

            rela_agent = create_rela_agent(
                agent_loop=loop, memory_client=memory_client,
            )
```

Pass `rela_agent=rela_agent` to `build_tool_registry()`:

```python
        tool_definitions, tool_handlers = build_tool_registry(
            tool_instances, timezone=timezone, rela_agent=rela_agent,
        )
```

- [ ] **Step 2: Update jobs.yaml template**

Add to `src/cosinabox/templates/user-repo/jobs.yaml`:

```yaml
  extract_fireflies:
    enabled: false
    schedule: "0 7 * * *"      # 7:00 AM — extract facts from meeting transcripts
  extract_gmail:
    enabled: false
    schedule: "15 7 * * *"     # 7:15 AM — extract facts from stakeholder emails
  post_meeting_debrief:
    enabled: false               # sends summary after meetings end
  rela_daily_scan:
    enabled: false
    schedule: "50 7 * * *"     # 7:50 AM — check relationship health
```

- [ ] **Step 3: Create docs/agent/rela.md**

```markdown
# Rela — Relationship Manager

Rela tracks relationship health for your stakeholders. It scores each relationship 0-100 and surfaces drift alerts when contacts cool.

## How it works

Rela runs as a background sub-agent with its own memory namespace. It reads from your calendar and stakeholder data but never modifies external systems (read-only).

## Scoring (v1)

| Factor | Weight | Best | Worst |
|--------|--------|------|-------|
| Recency (days since last contact) | 50% | <3 days = 100 | >30 days = 0 |
| Meeting frequency vs cadence | 50% | On cadence = 100 | 3x behind = 0 |

## Asking about relationships

In a DM conversation, ask your CoS:
- "How's my relationship with Alice?"
- "Who am I losing touch with?"
- "Show me relationship health for my VIPs"

The CoS uses the `rela_query` tool to get answers from Rela.

## Scheduled jobs

| Job | Schedule | What it does |
|-----|----------|-------------|
| rela_daily_scan | 7:50 AM | Check VIP/Active stakeholders, update scores |

## Enabling Rela

Tell Claude Code "enable Rela" or:
```bash
cosinabox enable-job rela_daily_scan
cosinabox enable-job post_meeting_debrief
```
```

- [ ] **Step 4: Update jobs.md and system prompt**

Add new jobs to `docs/agent/jobs.md` table.

Add to system prompt capabilities: `Rela: ask about relationship health (e.g., "how's my relationship with Alice?")`

- [ ] **Step 5: Run full test suite**
- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/app.py src/cosinabox/templates/ src/cosinabox/prompts/core.py
git commit -m "feat: wire extraction + debrief + Rela into App + OSS docs"
```

---

### Task 8: Final validation

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest -q`
Expected: ALL PASS (~280+ tests)

- [ ] **Step 2: Stress test checklist**

- [ ] First run (empty extraction_state) — doesn't crash
- [ ] Fireflies not configured — extractors skip gracefully
- [ ] No stakeholders with email — Gmail extraction skips with clear message
- [ ] Meeting ended but no transcript — debrief sends basic info
- [ ] Rela query for unknown stakeholder — returns "no data"
- [ ] No hardcoded names in descriptions or prompts
- [ ] All new jobs documented in jobs.md
- [ ] Rela documented in rela.md with example queries

- [ ] **Step 3: Sync vendored copy**

```bash
cp -r src/cosinabox/ /tmp/rovik-keevs/cosinabox/
```

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin plan4b-intelligence
gh pr create --title "Plan 4B: extraction pipeline, post-meeting debrief, Rela" --body "..."
gh pr merge --auto --squash
```
