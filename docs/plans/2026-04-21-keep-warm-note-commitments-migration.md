# Keep Warm note ↔ commitments migration — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the commitments table the sole authoritative home for commitments by defining a semantic boundary for `keep_warm_note`, surfacing existing leaks for migration, preventing re-accumulation via a soft-warn write-time guardrail + briefing-time detector, and snapshotting note changes to a history table.

**Spec:** [`docs/specs/2026-04-21-keep-warm-note-commitments-migration-design.md`](../specs/2026-04-21-keep-warm-note-commitments-migration-design.md)

**Architecture:** A pure-Python regex detector lives alongside a new migration module in `src/cosinabox/commitments/`. The existing Attio `set_keep_warm` tool handler (in `src/cosinabox/tools/registry.py`) is the single composition point: it snapshots the prior note into a new `keep_warm_note_history` SQLite table before delegating to `AttioClient`, and it appends a `WARNING:` line to its string response when the incoming note trips the regex. Two new agent tools (`keep_warm_review`, `keep_warm_history`) expose the migration and history features. The morning briefing's prefetch grows a tiny leak counter. `AttioClient` stays pure (no Memory coupling); orchestration lives in the registry handler.

**Tech Stack:** Python 3.11+, SQLite via `sqlite3` stdlib, pytest, ruff, mypy, Anthropic Claude tool-use (string-returning handlers).

---

## File map

### Created

- `src/cosinabox/memory/keep_warm_history.py` — CRUD for `keep_warm_note_history` (free functions, takes `Memory`, follows `commitments/store.py` pattern)
- `src/cosinabox/commitments/migrate_from_keep_warm.py` — regex detector (`looks_like_commitment`) + migration query (`list_flagged_keep_warm_notes`)
- `tests/unit/test_keep_warm_note_history.py` — history table CRUD
- `tests/unit/test_migrate_from_keep_warm.py` — regex positive/negative cases, migration-query shape

### Modified

- `src/cosinabox/memory/sqlite.py` — add `keep_warm_note_history` to `_SCHEMA` (runs on every `Memory()` init; `CREATE IF NOT EXISTS` is a no-op on existing DBs)
- `src/cosinabox/tools/registry.py` — update `keep_warm_set` tool description (semantic-boundary first line); extend `_build_attio_handlers` to accept `memory` and perform snapshot + regex-warn; add `keep_warm_review` and `keep_warm_history` tool definitions + handlers; thread `memory` through `build_tool_registry` (already a param)
- `src/cosinabox/tools/attio.py` — update `KeepWarmPerson.note` docstring only. `AttioClient.set_keep_warm` is NOT modified (keep CRM layer pure; orchestration belongs in the handler)
- `src/cosinabox/jobs/morning_briefing.py` — extend `_prefetch` with a regex scan over all keep-warm notes; emit `KEEP WARM — LEAKED: N …` when N>0
- `src/cosinabox/prompts/core.py` — add generalized "TOOL WARNINGS" rule
- `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` — note-vs-commitment line
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — note-vs-commitment line in the Keep Warm section
- `tests/unit/test_attio_keep_warm.py` — docstring test stays green (no changes expected; listed here because the file is relevant)

---

## Milestone 1 — Note history storage

Foundation. Pure-SQLite work; no Attio, no agent, no prompt changes. Lands first so M3's snapshot can call into it.

### Task 1.1: Add `keep_warm_note_history` table to `_SCHEMA`

**Files:**
- Modify: `src/cosinabox/memory/sqlite.py:22-208` (the `_SCHEMA` constant)
- Test: `tests/unit/test_keep_warm_note_history.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_keep_warm_note_history.py`:

```python
# ruff: noqa: I001
"""Tests for keep_warm_note_history table + CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from cosinabox.memory import Memory


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


def test_keep_warm_note_history_table_exists(db: Memory) -> None:
    """Memory init creates the keep_warm_note_history table."""
    with db.lock:
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("keep_warm_note_history",),
        )
        assert cur.fetchone() is not None


def test_keep_warm_note_history_schema(db: Memory) -> None:
    """Table has the expected columns."""
    with db.lock:
        cur = db._conn.execute("PRAGMA table_info(keep_warm_note_history)")
        cols = {row["name"]: row["type"] for row in cur.fetchall()}
    assert cols == {
        "id": "INTEGER",
        "person_record_id": "TEXT",
        "person_name": "TEXT",
        "note": "TEXT",
        "archived_at": "TEXT",
        "reason": "TEXT",
    }


def test_keep_warm_note_history_index_exists(db: Memory) -> None:
    """Composite index on (person_record_id, archived_at) exists for history lookups."""
    with db.lock:
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_kwh_person_time",),
        )
        assert cur.fetchone() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: `test_keep_warm_note_history_table_exists` FAILS — no such table.

- [ ] **Step 3: Add the table to `_SCHEMA`**

In `src/cosinabox/memory/sqlite.py`, append to the `_SCHEMA` string (after the `manual_closures` block, before the closing `"""`):

```sql

-- Keep Warm note history: snapshot on every note change through
-- set_keep_warm (via registry handler). Reason is nullable; left as a
-- forward-looking hook for distinguishing sources if ever needed. History
-- rows are small; no pruning in v1.
CREATE TABLE IF NOT EXISTS keep_warm_note_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_record_id  TEXT    NOT NULL,
    person_name       TEXT,
    note              TEXT    NOT NULL,
    archived_at       TEXT    NOT NULL,
    reason            TEXT
);
CREATE INDEX IF NOT EXISTS idx_kwh_person_time
    ON keep_warm_note_history (person_record_id, archived_at DESC);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/memory/sqlite.py tests/unit/test_keep_warm_note_history.py
git commit -m "$(cat <<'EOF'
feat(memory): add keep_warm_note_history table

Snapshot target for note changes on keep_warm people; populated by the
set_keep_warm handler in a subsequent commit. Schema uses CREATE IF NOT
EXISTS so existing DBs pick up the table on next Memory() init without a
manual migration step.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.2: Create `archive_note` function

**Files:**
- Create: `src/cosinabox/memory/keep_warm_history.py`
- Test: `tests/unit/test_keep_warm_note_history.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_keep_warm_note_history.py`:

```python
from datetime import datetime

from cosinabox.memory.keep_warm_history import archive_note, list_note_history


def test_archive_note_inserts_row(db: Memory) -> None:
    archive_note(
        db,
        person_record_id="rec_123",
        person_name="Sarah Chen",
        note="Send proposal by Friday",
        reason="user_update",
    )
    with db.lock:
        cur = db._conn.execute("SELECT * FROM keep_warm_note_history")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["person_record_id"] == "rec_123"
    assert rows[0]["person_name"] == "Sarah Chen"
    assert rows[0]["note"] == "Send proposal by Friday"
    assert rows[0]["reason"] == "user_update"
    # archived_at is a valid ISO-8601 UTC timestamp
    datetime.fromisoformat(rows[0]["archived_at"])


def test_archive_note_accepts_null_reason(db: Memory) -> None:
    archive_note(
        db,
        person_record_id="rec_1",
        person_name=None,
        note="old note",
        reason=None,
    )
    with db.lock:
        cur = db._conn.execute("SELECT reason, person_name FROM keep_warm_note_history")
        row = cur.fetchone()
    assert row["reason"] is None
    assert row["person_name"] is None


def test_archive_note_multiple_rows_for_same_person(db: Memory) -> None:
    """Same person gets multiple rows over time."""
    for text in ["first", "second", "third"]:
        archive_note(
            db,
            person_record_id="rec_x",
            person_name="X",
            note=text,
            reason=None,
        )
    with db.lock:
        cur = db._conn.execute(
            "SELECT COUNT(*) FROM keep_warm_note_history WHERE person_record_id = ?",
            ("rec_x",),
        )
        assert cur.fetchone()[0] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: ImportError — `cosinabox.memory.keep_warm_history` does not exist.

- [ ] **Step 3: Create the module with `archive_note`**

Create `src/cosinabox/memory/keep_warm_history.py`:

```python
"""CRUD for keep_warm_note_history.

Free functions operating on a ``Memory`` instance. Matches the
``commitments/store.py`` pattern (sync, dict returns, connection lock).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cosinabox.memory import Memory


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def archive_note(
    db: Memory,
    *,
    person_record_id: str,
    person_name: str | None,
    note: str,
    reason: str | None = None,
) -> None:
    """Insert one history row for a keep-warm note being overwritten.

    ``note`` is the PRIOR value being preserved — not the incoming one.
    ``reason`` is free-text context; today every archival is called from
    the set_keep_warm handler and passes None (placeholder for future use).
    """
    with db.lock:
        db._conn.execute(
            "INSERT INTO keep_warm_note_history "
            "(person_record_id, person_name, note, archived_at, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_record_id, person_name, note, _now_iso(), reason),
        )
        db._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: the three new tests PASS; the three from Task 1.1 still PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/memory/keep_warm_history.py tests/unit/test_keep_warm_note_history.py
git commit -m "$(cat <<'EOF'
feat(memory): archive_note CRUD for keep_warm_note_history

Free function taking a Memory instance, matching the commitments/store.py
convention. Callers pass the PRIOR note value before overwriting the live
record. Reason is nullable — no current caller populates it; reserved for
future extension.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1.3: Add `list_note_history` function

**Files:**
- Modify: `src/cosinabox/memory/keep_warm_history.py`
- Test: `tests/unit/test_keep_warm_note_history.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_list_note_history_returns_newest_first(db: Memory) -> None:
    """Rows come back newest-first based on archived_at DESC, ties broken by id DESC."""
    for text in ["oldest", "middle", "newest"]:
        archive_note(
            db,
            person_record_id="rec_abc",
            person_name="A",
            note=text,
            reason=None,
        )
    rows = list_note_history(db, person_record_id="rec_abc")
    assert [r["note"] for r in rows] == ["newest", "middle", "oldest"]


def test_list_note_history_filters_by_person(db: Memory) -> None:
    archive_note(db, person_record_id="rec_a", person_name="A", note="a1", reason=None)
    archive_note(db, person_record_id="rec_b", person_name="B", note="b1", reason=None)
    rows = list_note_history(db, person_record_id="rec_a")
    assert len(rows) == 1
    assert rows[0]["note"] == "a1"


def test_list_note_history_empty_when_no_rows(db: Memory) -> None:
    assert list_note_history(db, person_record_id="never") == []


def test_list_note_history_limit(db: Memory) -> None:
    for i in range(10):
        archive_note(
            db, person_record_id="rec_l", person_name="L", note=f"n{i}", reason=None
        )
    assert len(list_note_history(db, person_record_id="rec_l", limit=3)) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: ImportError on `list_note_history`.

- [ ] **Step 3: Implement `list_note_history`**

Append to `src/cosinabox/memory/keep_warm_history.py`:

```python
def list_note_history(
    db: Memory,
    *,
    person_record_id: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return archived notes for a person, newest first.

    Ties (same ``archived_at`` ISO string) are broken by ``id DESC``.
    """
    with db.lock:
        cur = db._conn.execute(
            "SELECT id, person_record_id, person_name, note, archived_at, reason "
            "FROM keep_warm_note_history "
            "WHERE person_record_id = ? "
            "ORDER BY archived_at DESC, id DESC LIMIT ?",
            (person_record_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/memory/keep_warm_history.py tests/unit/test_keep_warm_note_history.py
git commit -m "$(cat <<'EOF'
feat(memory): list_note_history for keep_warm_note_history

Newest-first read helper for the keep_warm_history agent tool (wired in a
later commit). Limit default of 25 keeps the agent response bounded.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Milestone 2 — Regex detector + migration query

Pure detection layer. No Attio wiring yet; gives M3/M4/M5 a single shared function to import.

### Task 2.1: Create `looks_like_commitment` regex + positive cases

**Files:**
- Create: `src/cosinabox/commitments/migrate_from_keep_warm.py`
- Test: `tests/unit/test_migrate_from_keep_warm.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_migrate_from_keep_warm.py`:

```python
# ruff: noqa: I001
"""Tests for keep_warm note → commitment migration detection + query."""

from __future__ import annotations

import pytest

from cosinabox.commitments.migrate_from_keep_warm import looks_like_commitment


@pytest.mark.parametrize(
    "text",
    [
        "Send proposal by Friday",
        "Follow up by EOD Monday",
        "Reply before next week",
        "Submit SOW by March 15",
        "Share the deck by Tuesday 5pm",
        "Email intro before EOW",
        "Respond by Q2",
        "Deliver draft next month",
        "Ping in 3 days",
        "Call back by Jan 15",
        "Follow up on Friday",
    ],
)
def test_looks_like_commitment_matches_deadline_phrases(text: str) -> None:
    matched = looks_like_commitment(text)
    assert matched is not None, f"expected match for: {text!r}"
    # Matched substring is from the input
    assert matched.lower() in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: ImportError — module does not exist.

- [ ] **Step 3: Implement the module with `looks_like_commitment`**

Create `src/cosinabox/commitments/migrate_from_keep_warm.py`:

```python
"""Keep Warm note ↔ commitments migration — detector and flagged-row query.

Detection (`looks_like_commitment`) is a pure-string regex operating on
free-text notes. Migration extraction (turning a flagged note into
structured commitments) happens in the agent loop, not here — the
`list_flagged_keep_warm_notes` helper just identifies which notes need
review so the agent can reason about each one conversationally.
"""

from __future__ import annotations

import re
from typing import Any

# Case-insensitive. Each alternative is a complete commitment-shaped
# phrase. Bias is toward false positives (soft-warn semantics); false
# negatives let leaks continue accumulating.
_WEEKDAY = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?"
_MONTH = (
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?"
)
_ACTION = (
    r"(?:send|reply|respond|share|submit|deliver|follow[\s-]?up|email|call|"
    r"ping|sign|intro|introduce)"
)

_PATTERNS = [
    # "by <weekday>", "before <weekday>", "on <weekday>"
    rf"\b(?:by|before|on|this|next)\s+{_WEEKDAY}\b",
    # "by EOD", "before EOW", "by EOM"
    r"\b(?:by|before)\s+(?:EO[DWM])\b",
    # "this week", "next week", "this month", "next month"
    r"\b(?:this|next)\s+(?:week|month|quarter)\b",
    # "in 3 days", "in 2 weeks", "in a month"
    r"\bin\s+(?:\d+|a|an|one|two|three|four|five)\s+(?:day|week|month)s?\b",
    # "by Q1".."by Q4"
    r"\bby\s+Q[1-4]\b",
    # "by <Month> <day>" e.g. "by Jan 15", "by March 15"
    rf"\bby\s+{_MONTH}\s+\d{{1,2}}\b",
    # Action verb + time-ish: "send X by", "reply X before"
    rf"\b{_ACTION}\b[^.!?\n]*?\b(?:by|before|this|next|in)\b",
    # Action verb + weekday: "follow up on Friday"
    rf"\b{_ACTION}\b[^.!?\n]*?\b(?:on|this|next|by|before)?\s*{_WEEKDAY}\b",
]

_COMBINED = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def looks_like_commitment(text: str | None) -> str | None:
    """Return the matched substring if ``text`` looks commitment-shaped, else None.

    The returned substring is the first match — used for the user-facing
    warning so they can see which phrase tripped the detector.
    """
    if not text:
        return None
    m = _COMBINED.search(text)
    return m.group(0) if m else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: all parametrized positive cases PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/commitments/migrate_from_keep_warm.py tests/unit/test_migrate_from_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(commitments): looks_like_commitment regex detector

Pure-string detector for commitment-shaped phrases in free-text notes:
deadline phrases (by <weekday|date|EOD|EOW|EOM|Qn>), relative-time
(this|next week|month|quarter; in N days|weeks), and action-verb + time
combos. Bias toward false positives — soft-warn semantics means a
spurious match is cheap while a false negative lets leaks through.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.2: Negative cases (pure status language must not match)

**Files:**
- Test: `tests/unit/test_migrate_from_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
@pytest.mark.parametrize(
    "text",
    [
        "SOW with Daniel is a key priority",
        "Lead Investor",
        "triathlete, son Oliver just started college",
        "introduced by Sarah in 2023; mentor for 5y",
        "SVP at Acme, owns Series B decision",
        "prospective Series A lead",
        "warm intro from Jake",
        "ex-colleague from Stripe",
        "",
        "    ",
    ],
)
def test_looks_like_commitment_ignores_pure_status(text: str) -> None:
    assert looks_like_commitment(text) is None, f"false positive on: {text!r}"


def test_looks_like_commitment_none_input() -> None:
    assert looks_like_commitment(None) is None


def test_looks_like_commitment_returns_first_match_substring() -> None:
    matched = looks_like_commitment("SOW is key. Send proposal by Friday. Thanks.")
    assert matched is not None
    assert "Friday" in matched or "by" in matched.lower()
```

- [ ] **Step 2: Run test to verify it fails (or already passes)**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: some negative cases may FAIL with the initial regex. Typical false-positive risk: `"introduced by Sarah in 2023"` could match "by Sarah" via the action-verb clause — inspect the failures and adjust.

- [ ] **Step 3: Tighten the regex if false-positives fire**

Likely adjustments to make in `src/cosinabox/commitments/migrate_from_keep_warm.py`:

- If `"introduced by Sarah"` trips the action-verb pattern, tighten `_ACTION` to exclude passive forms (`introduced`) and require the action be followed by a time word *within a bounded window* — e.g. change the pattern to `rf"\b{_ACTION}\b[^.!?\n]{{0,40}}?\b(?:by|before|this|next|in)\b"` AND add a negative-lookbehind requiring the "by" to not be an agent marker (the word immediately after "by" is not a proper noun — harder to express cleanly in regex; may need to drop "introduced" from `_ACTION`).
- If `"Lead Investor"` matches nothing, good.
- Iterate until all negative cases pass AND all positive cases from Task 2.1 still pass.

Do NOT remove patterns just to pass a single test — confirm the fix doesn't regress positives.

- [ ] **Step 4: Run both positive and negative test sets to confirm**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/commitments/migrate_from_keep_warm.py tests/unit/test_migrate_from_keep_warm.py
git commit -m "$(cat <<'EOF'
test(commitments): negative cases for looks_like_commitment

Pure status language (roles, personal facts, relationship color) must
not trip the detector. Tighten the action-verb pattern where needed to
eliminate false positives without regressing the deadline-phrase suite.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2.3: Add `list_flagged_keep_warm_notes` migration query

**Files:**
- Modify: `src/cosinabox/commitments/migrate_from_keep_warm.py`
- Test: `tests/unit/test_migrate_from_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
from types import SimpleNamespace


def _kw_person(
    *, name: str, record_id: str, note: str | None, days_since: int | None = 10,
    cadence_days: int = 14,
) -> SimpleNamespace:
    """Stand-in for attio.KeepWarmPerson with the fields we need."""
    return SimpleNamespace(
        name=name,
        record_id=record_id,
        cadence_days=cadence_days,
        note=note,
        last_interaction=None,
        days_since=days_since,
    )


class _StubAttio:
    def __init__(self, people: list[SimpleNamespace]) -> None:
        self.people = people

    def list_keep_warm(self) -> list[SimpleNamespace]:
        return list(self.people)


def test_list_flagged_keep_warm_notes_returns_only_flagged_rows() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    attio = _StubAttio(
        [
            _kw_person(name="Sarah", record_id="r1", note="Lead Investor"),
            _kw_person(name="Daniel", record_id="r2", note="Send proposal by Friday"),
            _kw_person(name="Amy", record_id="r3", note=None),
            _kw_person(name="Tom", record_id="r4", note="ex-colleague from Stripe"),
            _kw_person(name="Jane", record_id="r5", note="Follow up next week"),
        ]
    )
    flagged = list_flagged_keep_warm_notes(attio)
    names = {row["person"] for row in flagged}
    assert names == {"Daniel", "Jane"}


def test_list_flagged_keep_warm_notes_row_shape() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    attio = _StubAttio(
        [_kw_person(name="Daniel", record_id="r2", note="Send proposal by Friday")]
    )
    [row] = list_flagged_keep_warm_notes(attio)
    assert row["person"] == "Daniel"
    assert row["record_id"] == "r2"
    assert row["note"] == "Send proposal by Friday"
    assert row["regex_matches"] and all(m in row["note"].lower() or m in row["note"] for m in row["regex_matches"])
    assert row["days_since"] == 10
    assert row["cadence_days"] == 14


def test_list_flagged_keep_warm_notes_handles_attio_error() -> None:
    from cosinabox.commitments.migrate_from_keep_warm import list_flagged_keep_warm_notes

    class _Broken:
        def list_keep_warm(self) -> list[SimpleNamespace]:
            raise RuntimeError("Attio 500")

    assert list_flagged_keep_warm_notes(_Broken()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: ImportError on `list_flagged_keep_warm_notes`.

- [ ] **Step 3: Implement `list_flagged_keep_warm_notes`**

Append to `src/cosinabox/commitments/migrate_from_keep_warm.py`:

```python
import logging

logger = logging.getLogger(__name__)


def list_flagged_keep_warm_notes(attio: Any) -> list[dict[str, Any]]:
    """Return keep-warm people whose notes trip `looks_like_commitment`.

    Read-only: the agent loop walks the returned list to propose
    extractions conversationally. On any Attio error, returns [] — we
    never raise from this tool surface.
    """
    try:
        people = attio.list_keep_warm()
    except Exception:
        logger.warning("list_flagged_keep_warm_notes: Attio query failed", exc_info=True)
        return []

    flagged: list[dict[str, Any]] = []
    for p in people:
        note = getattr(p, "note", None)
        matched = looks_like_commitment(note)
        if matched is None:
            continue
        flagged.append(
            {
                "person": getattr(p, "name", ""),
                "record_id": getattr(p, "record_id", ""),
                "note": note,
                "regex_matches": [matched],
                "days_since": getattr(p, "days_since", None),
                "cadence_days": getattr(p, "cadence_days", None),
            }
        )
    return flagged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_migrate_from_keep_warm.py -v`

Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/commitments/migrate_from_keep_warm.py tests/unit/test_migrate_from_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(commitments): list_flagged_keep_warm_notes migration query

Read-only: enumerates keep-warm people whose notes match the regex
detector, returns structured rows for the agent to reason over. Attio
errors are swallowed (returns []) so the tool surface never raises.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Milestone 3 — Handler wiring: snapshot + regex warning + prompt rule

This is where the pieces compose. `AttioClient` stays pure; all orchestration lives in the registry handler.

### Task 3.1: Thread `memory` through `_build_attio_handlers`

**Files:**
- Modify: `src/cosinabox/tools/registry.py:544` (def `_build_attio_handlers`) and `src/cosinabox/tools/registry.py:675-678` (the Attio block in `build_tool_registry`)
- Test: no new test here — existing registry consistency check at `src/cosinabox/tools/registry.py:727-732` stays green

- [ ] **Step 1: Update `_build_attio_handlers` signature**

Change the signature in `src/cosinabox/tools/registry.py`:

```python
def _build_attio_handlers(
    attio: Any,
    *,
    memory: Any | None = None,
) -> dict[str, Callable[..., str]]:
```

And update the call site in `build_tool_registry`:

```python
    if "attio" in tool_instances:
        definitions.extend(ATTIO_TOOL_DEFINITIONS)
        handlers.update(_build_attio_handlers(tool_instances["attio"], memory=memory))
        logger.info("Registered %d Attio CRM tools", len(ATTIO_TOOL_DEFINITIONS))
```

- [ ] **Step 2: Run the full unit suite to confirm no regression**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/ -x -q`

Expected: existing tests PASS. Handler signature now accepts `memory` but nothing uses it yet.

- [ ] **Step 3: Commit**

```bash
git add src/cosinabox/tools/registry.py
git commit -m "$(cat <<'EOF'
refactor(tools/registry): thread memory into attio handler builder

Prep work for snapshot-on-write and the new keep_warm_history tool. No
behavior change — memory kwarg defaults to None and is unused in this
commit.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.2: Snapshot old note before Attio patch

**Files:**
- Modify: `src/cosinabox/tools/registry.py` — the `keep_warm_set` closure inside `_build_attio_handlers`
- Test: `tests/unit/test_tool_keep_warm.py` (append — this file already exists per the grep in spec research)

- [ ] **Step 1: Inspect the existing keep-warm handler test to match the fixture style**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v --collect-only`

Inspect the test file's stubs for Attio so the new test uses the same pattern (stub_attio with `get_person` / `set_keep_warm` / `list_keep_warm`).

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_tool_keep_warm.py` (use the existing stub helper in that file; the snippet below sketches the contract — adapt variable names to whatever the existing file already uses):

```python
def test_keep_warm_set_snapshots_old_note_when_changed(tmp_path) -> None:
    """When note changes, old note is snapshotted to keep_warm_note_history."""
    from cosinabox.memory import Memory
    from cosinabox.memory.keep_warm_history import list_note_history
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def __init__(self) -> None:
            self.patched = None

        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": "old note"}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            self.patched = {"person": person, "cadence": cadence_days, "note": note}
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_set"](person="Sarah", cadence_days=14, note="new note")
    assert "Sarah" in out  # happy string
    history = list_note_history(db, person_record_id="rec_1")
    assert len(history) == 1
    assert history[0]["note"] == "old note"


def test_keep_warm_set_no_snapshot_when_note_unchanged(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.memory.keep_warm_history import list_note_history
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": "same"}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    handlers["keep_warm_set"](person="Sarah", cadence_days=14, note="same")
    assert list_note_history(db, person_record_id="rec_1") == []


def test_keep_warm_set_no_snapshot_when_note_arg_omitted(tmp_path) -> None:
    """Caller leaves note=None → snapshot MUST NOT fire (cadence-only updates)."""
    from cosinabox.memory import Memory
    from cosinabox.memory.keep_warm_history import list_note_history
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": "existing"}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    handlers["keep_warm_set"](person="Sarah", cadence_days=14)  # no note kwarg
    assert list_note_history(db, person_record_id="rec_1") == []


def test_keep_warm_set_snapshots_when_clearing_note(tmp_path) -> None:
    """note='' is an explicit clear → old non-empty note MUST be archived."""
    from cosinabox.memory import Memory
    from cosinabox.memory.keep_warm_history import list_note_history
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": "old stuff"}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    handlers["keep_warm_set"](person="Sarah", cadence_days=14, note="")
    history = list_note_history(db, person_record_id="rec_1")
    assert len(history) == 1
    assert history[0]["note"] == "old stuff"


def test_keep_warm_set_no_memory_no_snapshot(tmp_path) -> None:
    """Handler built without memory still works (skips snapshot path)."""
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": "old"}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    handlers = _build_attio_handlers(_Attio(), memory=None)
    out = handlers["keep_warm_set"](person="Sarah", cadence_days=14, note="whatever")
    assert "Sarah" in out  # still works
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: new tests FAIL — snapshot logic not yet in handler.

- [ ] **Step 4: Update `keep_warm_set` handler to snapshot**

In `src/cosinabox/tools/registry.py`, replace the `keep_warm_set` function inside `_build_attio_handlers` (currently at lines ~570-577) with:

```python
    def keep_warm_set(person: str, cadence_days: int, note: str | None = None) -> str:
        # Read current note BEFORE delegating so we can snapshot a change
        current_note: str | None = None
        current_record_id: str | None = None
        if memory is not None and note is not None:
            try:
                profile = attio.get_person(person)
                if profile:
                    current_note = profile.get("keep_warm_note")
                    current_record_id = str(profile.get("id") or "") or None
            except Exception:
                logger.warning(
                    "keep_warm_set: pre-fetch for history snapshot failed",
                    exc_info=True,
                )

        try:
            out = attio.set_keep_warm(person=person, cadence_days=cadence_days, note=note)
        except Exception as exc:
            return f"keep_warm_set failed: {exc}"
        if out.get("status") != "ok":
            return f"keep_warm_set failed: {out.get('message', 'unknown')}"

        # Snapshot old note if it existed AND the incoming value differs
        if (
            memory is not None
            and note is not None
            and current_note
            and current_note != note
            and (current_record_id or out.get("record_id"))
        ):
            try:
                from cosinabox.memory.keep_warm_history import archive_note

                archive_note(
                    memory,
                    person_record_id=current_record_id or str(out.get("record_id", "")),
                    person_name=person,
                    note=current_note,
                    reason=None,
                )
            except Exception:
                logger.warning(
                    "keep_warm_set: history archive failed", exc_info=True
                )

        return f"Flagged {out['person']} as Keep Warm (cadence: {out['cadence_days']}d)."
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v && PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_keep_warm_note_history.py -v`

Expected: all snapshot tests PASS; history tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/tools/registry.py tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(tools/registry): snapshot note changes to keep_warm_note_history

set_keep_warm handler reads the current note before patching Attio; when
the incoming note differs from the stored one, the prior value is
archived to keep_warm_note_history. Snapshot is skipped when note is
None (cadence-only updates), when memory isn't wired in, or when values
are identical. Explicit note='' archives the prior non-empty value.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.3: Regex warning in `keep_warm_set` response

**Files:**
- Modify: `src/cosinabox/tools/registry.py` — same `keep_warm_set` closure
- Test: `tests/unit/test_tool_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tool_keep_warm.py`:

```python
def test_keep_warm_set_appends_warning_line_when_note_is_commitment_shaped(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": None}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_set"](
        person="Daniel", cadence_days=14, note="Send proposal by Friday"
    )
    assert "Daniel" in out  # happy line still present
    assert "WARNING:" in out  # warning line present
    assert "Friday" in out or "by" in out.lower()  # matched substring surfaced


def test_keep_warm_set_no_warning_on_pure_status_note(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": None}

        def set_keep_warm(self, *, person, cadence_days, note=None):
            return {"status": "ok", "record_id": "rec_1", "person": person, "cadence_days": cadence_days}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_set"](
        person="Sarah", cadence_days=14, note="Lead Investor"
    )
    assert "WARNING:" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: the two new tests FAIL — handler does not yet emit `WARNING:`.

- [ ] **Step 3: Append the warning line**

In `src/cosinabox/tools/registry.py`, update the `keep_warm_set` closure's return statement. Change:

```python
        return f"Flagged {out['person']} as Keep Warm (cadence: {out['cadence_days']}d)."
```

to:

```python
        lines = [f"Flagged {out['person']} as Keep Warm (cadence: {out['cadence_days']}d)."]
        if note:
            from cosinabox.commitments.migrate_from_keep_warm import looks_like_commitment

            matched = looks_like_commitment(note)
            if matched:
                lines.append(
                    f"WARNING: note looks commitment-shaped (\"{matched}\") — "
                    "consider calling commitment_create instead and keeping the "
                    "note as relationship context only."
                )
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/tools/registry.py tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(tools/registry): soft-warn when note looks commitment-shaped

keep_warm_set appends a WARNING: line to its response when the incoming
note trips the looks_like_commitment regex. The Attio write still
succeeds — engine does not veto explicit user updates. Prompt rule wired
in next commit tells the agent to surface WARNING lines to the user.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.4: Generalized prompt rule to surface `WARNING:` lines

**Files:**
- Modify: `src/cosinabox/prompts/core.py` — append a rule to `_SYSTEM_PROMPT_SRC`
- Test: `tests/unit/test_prompts.py` (append) — the file exists per prior grep

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_prompts.py`:

```python
def test_system_prompt_includes_tool_warnings_rule() -> None:
    from cosinabox.prompts.core import render_system_prompt

    rendered = render_system_prompt(
        personality="(test)", name="Sam", timezone="UTC"
    )
    assert "WARNING:" in rendered
    # Instruction must cover both surfacing and not-ignoring
    assert "surface" in rendered.lower() or "show" in rendered.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_prompts.py -v -k tool_warnings`

Expected: FAIL — prompt doesn't mention `WARNING:`.

- [ ] **Step 3: Add the rule**

In `src/cosinabox/prompts/core.py`, insert a new section between the `HONESTY:` block and the `COMMITMENT CAPTURE` block (at roughly line 60):

```python
TOOL WARNINGS:
- If a tool response contains a line starting with "WARNING:", surface
  that line verbatim to the user and ask how they want to proceed before
  moving on. The tool already executed; the warning is informational —
  not an error.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_prompts.py -v`

Expected: all prompt tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/prompts/core.py tests/unit/test_prompts.py
git commit -m "$(cat <<'EOF'
feat(prompts): surface tool WARNING lines to the user

Generalized rule — not specific to keep_warm — so any future tool can
emit an informational 'WARNING:' line and trust the agent to ask the
user how to proceed instead of silently swallowing it.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Milestone 4 — New agent tools + semantic boundary documentation

Exposes the migration and history features to the agent, and bakes the semantic boundary into the load-bearing copy.

### Task 4.1: Register `keep_warm_review` tool

**Files:**
- Modify: `src/cosinabox/tools/registry.py` — append to `ATTIO_TOOL_DEFINITIONS`; add handler in `_build_attio_handlers`
- Test: `tests/unit/test_tool_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_keep_warm_review_returns_flagged_rows(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.attio import KeepWarmPerson
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def list_keep_warm(self) -> list[KeepWarmPerson]:
            return [
                KeepWarmPerson(
                    name="Sarah", record_id="r1", cadence_days=14,
                    note="Lead Investor", last_interaction=None, days_since=5,
                ),
                KeepWarmPerson(
                    name="Daniel", record_id="r2", cadence_days=14,
                    note="Send proposal by Friday",
                    last_interaction=None, days_since=20,
                ),
            ]

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_review"]()
    assert "Daniel" in out
    assert "Sarah" not in out
    assert "Friday" in out or "by" in out.lower()


def test_keep_warm_review_empty_when_no_leaks(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.attio import KeepWarmPerson
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def list_keep_warm(self) -> list[KeepWarmPerson]:
            return [
                KeepWarmPerson(
                    name="Sarah", record_id="r1", cadence_days=14,
                    note="Lead Investor", last_interaction=None, days_since=5,
                ),
            ]

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_review"]()
    assert "no" in out.lower() or "empty" in out.lower() or out.strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v -k review`

Expected: KeyError / AttributeError — no such handler.

- [ ] **Step 3: Register definition + handler**

In `src/cosinabox/tools/registry.py`, append to `ATTIO_TOOL_DEFINITIONS`:

```python
    {
        "name": "keep_warm_review",
        "description": (
            "Scan all Keep Warm people for notes that look commitment-shaped "
            "(deadline or action-verb phrases) and return them so the user "
            "can decide whether to extract them into the commitments table. "
            "Use when the user asks to clean up Keep Warm notes, or when "
            "the morning briefing surfaces a KEEP WARM — LEAKED count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
```

Add to `_build_attio_handlers` (inside the function, before the `return` statement):

```python
    def keep_warm_review() -> str:
        from cosinabox.commitments.migrate_from_keep_warm import (
            list_flagged_keep_warm_notes,
        )

        flagged = list_flagged_keep_warm_notes(attio)
        if not flagged:
            return "No Keep Warm notes look commitment-shaped."
        lines = [f"{len(flagged)} Keep Warm note(s) look commitment-shaped:"]
        for row in flagged:
            lines.append(
                f"- {row['person']} — note: \"{row['note']}\" "
                f"(matched: {', '.join(row['regex_matches'])})"
            )
        lines.append(
            "\nFor each, propose extracting a commitment (commitment_create) "
            "and rewriting the note to relationship context only (keep_warm_set "
            "with the cleaned note). Ask the user to approve each before applying."
        )
        return "\n".join(lines)
```

And add to the returned dict:

```python
    return {
        "crm_search_people": crm_search_people,
        ...
        "keep_warm_list": keep_warm_list,
        "keep_warm_review": keep_warm_review,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: all tests PASS. The registry consistency check in `build_tool_registry` also passes (definition and handler names match).

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/tools/registry.py tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(tools): keep_warm_review agent tool

Read-only. Returns Keep Warm people whose notes trip the commitment
detector, with instructions for the agent to walk the list
conversationally and apply per-item approvals via commitment_create +
keep_warm_set.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.2: Register `keep_warm_history` tool

**Files:**
- Modify: `src/cosinabox/tools/registry.py` — append to `ATTIO_TOOL_DEFINITIONS`; add handler
- Test: `tests/unit/test_tool_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_keep_warm_history_returns_archived_notes(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.memory.keep_warm_history import archive_note
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": None}

    db = Memory(db_path=tmp_path / "test.db")
    for text in ["oldest", "middle", "newest"]:
        archive_note(
            db, person_record_id="rec_1", person_name="Sarah",
            note=text, reason=None,
        )

    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_history"](person="Sarah")
    # Newest appears first
    assert out.index("newest") < out.index("middle") < out.index("oldest")


def test_keep_warm_history_empty_when_no_records(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str) -> dict:
            return {"id": "rec_1", "name": name, "keep_warm_note": None}

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_history"](person="Sarah")
    assert "no" in out.lower() or "history" in out.lower()


def test_keep_warm_history_person_not_found(tmp_path) -> None:
    from cosinabox.memory import Memory
    from cosinabox.tools.registry import _build_attio_handlers

    class _Attio:
        def get_person(self, name: str):
            return None

    db = Memory(db_path=tmp_path / "test.db")
    handlers = _build_attio_handlers(_Attio(), memory=db)
    out = handlers["keep_warm_history"](person="Ghost")
    assert "not found" in out.lower() or "no person" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v -k history`

Expected: FAIL — no such handler.

- [ ] **Step 3: Register definition + handler**

Append to `ATTIO_TOOL_DEFINITIONS`:

```python
    {
        "name": "keep_warm_history",
        "description": (
            "Return archived keep-warm notes for a person, newest-first. "
            "Use when the user asks what the note for someone USED to say, "
            "or to confirm a prior cleanup was intentional."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Person's name."},
            },
            "required": ["person"],
        },
    },
```

Add to `_build_attio_handlers`:

```python
    def keep_warm_history(person: str) -> str:
        if memory is None:
            return "keep_warm_history unavailable: memory/db not configured."
        try:
            profile = attio.get_person(person)
        except Exception as exc:
            return f"keep_warm_history failed: {exc}"
        if not profile:
            return f"No person found matching '{person}'."
        record_id = str(profile.get("id") or "")
        if not record_id:
            return f"No record id for '{person}'."

        from cosinabox.memory.keep_warm_history import list_note_history

        rows = list_note_history(memory, person_record_id=record_id)
        if not rows:
            return f"No archived note history for {person}."
        lines = [f"{len(rows)} archived note(s) for {person} (newest first):"]
        for r in rows:
            lines.append(f"- [{r['archived_at']}] {r['note']}")
        return "\n".join(lines)
```

Add to the returned dict alongside `keep_warm_review`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/tools/registry.py tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
feat(tools): keep_warm_history agent tool

Returns archived note versions for a person, newest-first. Lets the user
recall what a note used to say before a cleanup or evolution.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.3: Update `keep_warm_set` tool description + `KeepWarmPerson.note` docstring with the semantic boundary

**Files:**
- Modify: `src/cosinabox/tools/registry.py` — the `keep_warm_set` entry in `ATTIO_TOOL_DEFINITIONS` (around line 275-298)
- Modify: `src/cosinabox/tools/attio.py` — the `KeepWarmPerson` dataclass
- Test: `tests/unit/test_tool_keep_warm.py` (append)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_keep_warm_set_tool_description_contains_semantic_boundary() -> None:
    from cosinabox.tools.registry import ATTIO_TOOL_DEFINITIONS

    defn = next(d for d in ATTIO_TOOL_DEFINITIONS if d["name"] == "keep_warm_set")
    desc = defn["description"]
    assert "relationship context" in desc.lower()
    assert "commitment" in desc.lower()
    # Note input-schema description also carries the rule
    note_desc = defn["input_schema"]["properties"]["note"]["description"]
    assert "no deadlines" in note_desc.lower() or "relationship" in note_desc.lower()


def test_keep_warm_person_note_docstring_contains_semantic_boundary() -> None:
    from cosinabox.tools.attio import KeepWarmPerson
    import inspect

    doc = inspect.getdoc(KeepWarmPerson) or ""
    # Dataclass-level doc may cover it; if note has a per-field doc, check that
    # instead. At minimum, the concept must appear somewhere readable.
    combined = doc + " " + (KeepWarmPerson.__doc__ or "")
    assert "relationship context" in combined.lower()
    assert "commitment" in combined.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v -k semantic_boundary`

Expected: FAIL — the load-bearing copy isn't in place.

- [ ] **Step 3: Update the tool description**

In `src/cosinabox/tools/registry.py`, replace the `keep_warm_set` entry's `description` with:

```python
        "description": (
            "Flag a person as Keep Warm with a per-person cadence in days. "
            "NOTE FIELD = relationship context: who they are, how you know "
            "them, what they care about, what makes this relationship current. "
            "NO future-tense actions, NO deadlines, NO items you owe them — "
            "if a line tells you what to DO or WHEN, it's a commitment; track "
            "it via commitment_create instead. The morning briefing surfaces "
            "overdue Keep Warm people. Use when the user asks to remember "
            "someone (e.g., 'remind me to stay in touch with Sarah every two "
            "weeks'). Cadence is clamped to [1, 365]."
        ),
```

Update the `note` property in the same definition's `input_schema`:

```python
                "note": {
                    "type": "string",
                    "description": (
                        "Optional short relationship-context note (e.g., "
                        "'Lead investor', 'triathlete, met at YC W22'). "
                        "NO deadlines or action items — use commitment_create "
                        "for those."
                    ),
                },
```

In `src/cosinabox/tools/attio.py`, update the `KeepWarmPerson` dataclass docstring:

```python
@dataclass
class KeepWarmPerson:
    """Typed view for a Keep Warm-flagged person.

    The ``note`` field carries RELATIONSHIP CONTEXT only — who they are,
    how you know them, what they care about, what makes this relationship
    current. No future-tense actions, no deadlines, no items owed. Those
    belong in the commitments table (see ``cosinabox.commitments``).
    """

    name: str
    record_id: str
    cadence_days: int
    note: str | None
    last_interaction: str | None
    days_since: int | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/tools/registry.py src/cosinabox/tools/attio.py tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
docs(tools): semantic boundary for keep_warm note

Agent-facing tool description for keep_warm_set and the input_schema
note field both spell out the note-vs-commitment rule explicitly. The
KeepWarmPerson docstring echoes the same rule for human readers. These
are the load-bearing strings that the agent and future contributors
actually read.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4.4: User-repo template docs

**Files:**
- Modify: `src/cosinabox/templates/user-repo/docs/agent/editing-config.md`
- Modify: `src/cosinabox/templates/user-repo/docs/agent/jobs.md`
- Test: `tests/unit/test_tool_keep_warm.py` (append — simple string-presence checks)

- [ ] **Step 1: Find the relevant sections**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH grep -n "keep.warm\|Keep Warm" src/cosinabox/templates/user-repo/docs/agent/editing-config.md src/cosinabox/templates/user-repo/docs/agent/jobs.md`

Identify where Keep Warm is already documented in each file. Read the surrounding context (~10 lines) so the new sentence lands in the right place.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_tool_keep_warm.py`:

```python
def test_user_repo_editing_config_mentions_note_boundary() -> None:
    from pathlib import Path
    from cosinabox import templates

    root = Path(templates.__file__).parent / "user-repo"
    text = (root / "docs/agent/editing-config.md").read_text()
    # Key rule must be present (phrasing may vary)
    assert "relationship context" in text.lower()
    assert "commitment" in text.lower()


def test_user_repo_jobs_doc_mentions_note_boundary() -> None:
    from pathlib import Path
    from cosinabox import templates

    root = Path(templates.__file__).parent / "user-repo"
    text = (root / "docs/agent/jobs.md").read_text()
    assert "keep warm" in text.lower()
    # The specific boundary sentence
    assert "relationship context" in text.lower() or "no deadlines" in text.lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v -k user_repo`

Expected: FAIL.

- [ ] **Step 4: Update both docs**

In `src/cosinabox/templates/user-repo/docs/agent/editing-config.md`, locate the Keep Warm section (from step 1) and append:

```markdown
### Keep Warm notes — what belongs there

The `note` field on a Keep Warm person is **relationship context**: who they are, how you know them, what they care about, what makes this relationship current. Examples that belong: `"Lead investor, introduced by Sarah"`, `"triathlete, son Oliver just started college"`, `"SVP at Acme, owns Series B decision"`.

**What does NOT belong**: future-tense actions, deadlines, or items you owe them. If a line tells the engine what to DO or WHEN, it's a commitment. Ask Claude to `commitment_create` instead, and keep the note as pure context.

If you write commitment-shaped text into a note, `keep_warm_set` will surface a `WARNING:` line and the next morning briefing will flag a `KEEP WARM — LEAKED` count. Run `keep_warm_review` to walk through and clean up.
```

In `src/cosinabox/templates/user-repo/docs/agent/jobs.md`, locate the Keep Warm mention and add the one-liner:

```markdown
**Note field rule:** relationship context only. No deadlines, no action items — those go in the commitments table. See `editing-config.md` for the full rule.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_tool_keep_warm.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/editing-config.md src/cosinabox/templates/user-repo/docs/agent/jobs.md tests/unit/test_tool_keep_warm.py
git commit -m "$(cat <<'EOF'
docs(user-repo): keep-warm note vs commitment rule

The same semantic boundary that lives in the keep_warm_set tool
description is mirrored in the user-facing agent docs so users
interacting with config via Claude (or reading the template for the
first time) see the rule without needing to dig into source.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Milestone 5 — Briefing-time leak detector

Closes the gap for notes edited directly in Attio's web UI (which bypass `set_keep_warm` entirely).

### Task 5.1: Extend `MorningBriefingJob._prefetch` with a leak-count line

**Files:**
- Modify: `src/cosinabox/jobs/morning_briefing.py` — the `_prefetch` method (lines 37-160)
- Test: `tests/unit/test_jobs_morning_briefing.py` (append — this file already exists per earlier grep)

- [ ] **Step 1: Inspect the existing briefing test fixture**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_jobs_morning_briefing.py -v --collect-only`

Find the fixture pattern used to build the briefing (stubbed `gmail`, `calendar`, `attio`, etc.) — reuse it so the new test is consistent.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_jobs_morning_briefing.py` (adapt variable names to the existing test-file style):

```python
def test_prefetch_emits_keep_warm_leaked_line_when_flagged_notes_exist(tmp_path) -> None:
    from cosinabox.jobs.morning_briefing import MorningBriefingJob
    from cosinabox.tools.attio import KeepWarmPerson

    class _Gmail:
        def list_recent(self, hours=12, max_results=15): return []
        def list_threads_needing_reply(self, hours=24, max_results=10): return []

    class _Cal:
        def list_events(self, start, end): return []

    class _Attio:
        def list_keep_warm(self):
            return [
                KeepWarmPerson(name="Sarah", record_id="r1", cadence_days=14,
                               note="Lead Investor", last_interaction=None, days_since=5),
                KeepWarmPerson(name="Daniel", record_id="r2", cadence_days=14,
                               note="Send proposal by Friday",
                               last_interaction=None, days_since=20),
                KeepWarmPerson(name="Jane", record_id="r3", cadence_days=14,
                               note="Follow up next week",
                               last_interaction=None, days_since=3),
            ]
        def get_keep_warm_overdue(self):
            # Only return the overdue row so the existing OVERDUE block has content
            return [r for r in self.list_keep_warm() if r.days_since and r.days_since > r.cadence_days]

    class _AgentLoop:
        def run(self, prompt, session_id): raise NotImplementedError("not reached in _prefetch-only test")

    job = MorningBriefingJob(
        gmail=_Gmail(), calendar=_Cal(), agent_loop=_AgentLoop(),
        personality="", name_for_briefing="Tester",
        attio=_Attio(), db=None, drive=None,
    )
    prefetched = job._prefetch()
    assert "KEEP WARM — LEAKED: 2" in prefetched  # Daniel + Jane
    assert "Ask me to review" in prefetched


def test_prefetch_emits_no_leaked_line_when_clean(tmp_path) -> None:
    from cosinabox.jobs.morning_briefing import MorningBriefingJob
    from cosinabox.tools.attio import KeepWarmPerson

    class _Gmail:
        def list_recent(self, hours=12, max_results=15): return []
        def list_threads_needing_reply(self, hours=24, max_results=10): return []

    class _Cal:
        def list_events(self, start, end): return []

    class _Attio:
        def list_keep_warm(self):
            return [
                KeepWarmPerson(name="Sarah", record_id="r1", cadence_days=14,
                               note="Lead Investor", last_interaction=None, days_since=5),
            ]
        def get_keep_warm_overdue(self): return []

    class _AgentLoop:
        def run(self, prompt, session_id): raise NotImplementedError

    job = MorningBriefingJob(
        gmail=_Gmail(), calendar=_Cal(), agent_loop=_AgentLoop(),
        personality="", name_for_briefing="Tester",
        attio=_Attio(), db=None, drive=None,
    )
    prefetched = job._prefetch()
    assert "LEAKED" not in prefetched
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_jobs_morning_briefing.py -v -k leaked`

Expected: FAIL — no such line in output.

- [ ] **Step 4: Add the leak scan**

In `src/cosinabox/jobs/morning_briefing.py`, inside `_prefetch`, extend the existing `self.attio is not None` block (at lines 114-129). After the overdue-rendering code, add:

```python
            # Leak detector: notes that look commitment-shaped. Catches
            # Attio web-UI edits that bypass the write-time guardrail in
            # keep_warm_set. Pure regex — no LLM cost; only emitted when > 0.
            try:
                from cosinabox.commitments.migrate_from_keep_warm import (
                    looks_like_commitment,
                )

                all_kw = self.attio.list_keep_warm()
                leaked = sum(1 for p in all_kw if looks_like_commitment(p.note))
                if leaked:
                    sections.append(
                        f"KEEP WARM — LEAKED: {leaked} notes look "
                        "commitment-shaped. Ask me to review."
                    )
            except Exception:
                pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/test_jobs_morning_briefing.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/jobs/morning_briefing.py tests/unit/test_jobs_morning_briefing.py
git commit -m "$(cat <<'EOF'
feat(jobs/morning_briefing): KEEP WARM LEAKED count in prefetch

Runs the commitment-detection regex over every keep-warm person's note,
appends a single-line count to the briefing prefetch when non-zero.
Closes the gap left by the write-time guardrail, which only fires on
agent-mediated set_keep_warm calls — notes edited in Attio's web UI now
surface on the next morning briefing.

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Milestone 6 — End-to-end validation + PR

### Task 6.1: Full test + lint + type-check pass

- [ ] **Step 1: Run the full unit suite**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH pytest tests/unit/ -x -q`

Expected: all tests PASS, including the existing suite. If something regresses, stop and investigate — per the brief, failures are investigated, not papered over.

- [ ] **Step 2: Run ruff**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH ruff check src tests && PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH ruff format --check src tests`

Expected: clean. Fix any findings; do not `--no-verify`.

- [ ] **Step 3: Run mypy**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH mypy src/cosinabox`

Expected: clean. Common fix: the new `_build_attio_handlers(memory=None)` needs `memory: Any | None = None` (not `Memory | None`, which would force a circular import concern — the commitments store uses `Any` too).

- [ ] **Step 4: CLI smoke test**

Run: `PATH=/Users/rovikrobert/code/cosinabox/.venv/bin:$PATH cosinabox --help`

Expected: no import errors from the new modules.

- [ ] **Step 5: Commit any lint/type fixups needed**

If steps 2-4 surfaced fixups:

```bash
git add <modified files>
git commit -m "$(cat <<'EOF'
chore: address lint/type findings for keep-warm migration

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If nothing to fix, skip.

### Task 6.2: Push and open PR with auto-merge

- [ ] **Step 1: Push the branch**

Run: `cd /Users/rovikrobert/.worktrees/cosinabox/feat-keep-warm-note-migration && git push -u origin feat/keep-warm-note-migration`

Expected: branch pushed.

- [ ] **Step 2: Open the PR**

Run:

```bash
cd /Users/rovikrobert/.worktrees/cosinabox/feat-keep-warm-note-migration && gh pr create --title "feat: keep-warm note ↔ commitments migration" --body "$(cat <<'EOF'
## Summary

- Make the `commitments` table the sole source of truth by preventing commitment-shaped text from accumulating in keep-warm notes.
- Soft-warn write-time guardrail on `keep_warm_set` — response appends a `WARNING:` line when the note trips a regex; write still succeeds.
- Briefing-time leak detector emits `KEEP WARM — LEAKED: N` in the morning briefing prefetch so Attio web-UI edits don't silently re-accumulate.
- New agent tools: `keep_warm_review` (walk flagged notes conversationally), `keep_warm_history` (recall archived notes).
- Snapshot-on-write note history table (`keep_warm_note_history`) preserves relationship context across cleanups and evolution.

Spec: `docs/specs/2026-04-21-keep-warm-note-commitments-migration-design.md`
Plan: `docs/plans/2026-04-21-keep-warm-note-commitments-migration.md`

## Test plan

- [ ] `pytest tests/unit/` — full unit suite green
- [ ] `ruff check src tests && ruff format --check src tests` — clean
- [ ] `mypy src/cosinabox` — clean
- [ ] `cosinabox --help` runs without import errors
- [ ] Manual: populate a keep-warm person with `"Send proposal by Friday"`, run the morning briefing, verify `KEEP WARM — LEAKED: 1` appears; invoke `keep_warm_review`, verify the row is listed; simulate an approve flow (agent calls `commitment_create` + `keep_warm_set(note=<cleaned>)`), verify archived note lands in `keep_warm_note_history` and the next briefing has no leaked count.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" && gh pr merge --auto --squash
```

Expected: PR opens and is queued for auto-merge after CI green.

---

## Self-review checklist — run before handoff

- **Spec coverage:** every spec section maps to at least one task
  - §1 Write-time guardrail → Task 3.3 (warning), Task 4.3 (description)
  - §2 Migration tool → Tasks 2.1-2.3, 4.1
  - §3 Briefing-time leak detector → Task 5.1
  - §4 Note history → Tasks 1.1-1.3, 3.2, 4.2
  - Semantic boundary → Tasks 4.3, 4.4
  - Generalized tool-warning prompt rule → Task 3.4
- **No placeholders:** all code blocks are complete; no "TBD" or "fill in".
- **Consistency:** function names used across tasks (`archive_note`, `list_note_history`, `looks_like_commitment`, `list_flagged_keep_warm_notes`, `keep_warm_review`, `keep_warm_history`) match their definitions.

## Open risks surfaced during planning

- **Memory-Attio coupling:** the handler reads the current note via `attio.get_person(person)` before calling `attio.set_keep_warm`. That's one extra HTTP round-trip on every `keep_warm_set` call. Acceptable — keep-warm edits are rare (handful per day at most) and the call happens in the same process.
- **Test fixture drift:** `tests/unit/test_tool_keep_warm.py` and `tests/unit/test_jobs_morning_briefing.py` pre-exist with their own stub conventions. Task 3.2 and Task 5.1 ask the implementer to adapt variable names to match the existing file — the snippets here sketch the contract.
- **Regex tuning:** Task 2.2 may require multiple iterations of pattern adjustment. If it does, keep every intermediate test green for the positive cases in Task 2.1 — don't trade one pass for another.
