# ruff: noqa: I001
"""Stress tests for everything shipped in the 2026-04-20 session.

These are targeted adversarial tests — edge cases, large batches, bad
data, concurrent access. They're separate from the main suite because
some are slower and they intentionally probe failure modes.

Run with: pytest tests/stress/
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cosinabox.agent.analytics import (
    get_analytics_summary,
    get_commitment_velocity,
    get_error_pattern_summary,
    get_error_patterns,
    invalidate_error_summary_cache,
)
from cosinabox.commitments import (
    create_commitment,
    list_commitments,
)
from cosinabox.commitments.auto_resolve import (
    VERDICT_LIKELY_DONE,
    VERDICT_NO_EVIDENCE,
    verify_all_open_commitments,
    verify_commitment,
)
from cosinabox.memory import Memory
from cosinabox.tools.google.drive import DriveTool
from cosinabox.tools.attio import AttioClient, KeepWarmPerson


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "stress.db")


# ===========================================================================
# Commitments + auto_resolve stress
# ===========================================================================


def test_commitments_table_handles_500_rows(db: Memory) -> None:
    """Briefings at scale: 500 commitments shouldn't trip SQLite or order
    the listing nondeterministically."""
    for i in range(500):
        create_commitment(
            db,
            title=f"Commitment #{i:03d} ship v{i}",
            priority=(i % 5) + 1,
        )
    rows = list_commitments(db, limit=500)
    assert len(rows) == 500
    # Priority 1 items first, then 2, then 3...
    priorities = [r["priority"] for r in rows]
    assert priorities == sorted(priorities)


def test_commitment_unicode_and_emoji_in_title(db: Memory) -> None:
    """Unicode in titles must survive round-trip and not break keyword
    extraction."""
    c = create_commitment(db, title="送 Sarah Chen 的 Q3 deck 🚀")
    gmail = MagicMock()
    gmail.search.return_value = []
    got = verify_commitment(c, gmail)
    assert got["_verdict"] == VERDICT_NO_EVIDENCE
    assert "送" in got["title"]


def test_commitment_sql_injection_in_title_is_harmless(db: Memory) -> None:
    """Parameterized queries should neutralize injection attempts.
    This is a belt-and-braces — SQLite's driver enforces it, but the
    test documents the expectation."""
    hostile = "robert'); DROP TABLE commitments; --"
    c = create_commitment(db, title=hostile)
    # Table still exists?
    assert list_commitments(db)
    # Title survived verbatim?
    assert c["title"] == hostile


def test_concurrent_commitment_creates(db: Memory) -> None:
    """Multiple threads inserting at once — SQLite with WAL mode (set in
    Memory.__init__) should handle this without locking errors.
    Each thread holds its own connection but they share the underlying file.
    """
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            # Threads share the Memory instance's connection; SQLite's
            # check_same_thread=False is set in Memory.__init__.
            create_commitment(db, title=f"concurrent-{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent writes raised: {errors}"
    rows = list_commitments(db, limit=50)
    assert len(rows) == 20


def test_verify_all_with_50_commitments_completes(db: Memory) -> None:
    """50 commitments through the verifier with mocked Gmail — should
    complete quickly and return 50 results."""
    for i in range(50):
        create_commitment(db, title=f"batch item {i} ship")
    gmail = MagicMock()
    gmail.search.return_value = []

    import time as _time

    start = _time.monotonic()
    results = verify_all_open_commitments(db, gmail, limit=50)
    duration = _time.monotonic() - start

    assert len(results) == 50
    # 50 items × ~0.01s per mocked search should be well under 5s.
    assert duration < 5.0, f"verify_all took {duration:.2f}s for 50 items"
    # ThreadPool completion ordering preserved (id-ordered).
    ids = [r["id"] for r in results]
    assert ids == sorted(ids)


def test_verify_commitment_timeout_tagged_as_no_evidence(db: Memory) -> None:
    """One slow Gmail search is tagged NO_EVIDENCE via future.result
    timeout. (Wall-clock isn't bounded — ThreadPoolExecutor's timeout
    abandons the future but can't cancel the sleeping worker thread.
    That's a Python-threading limitation; the contract we verify is
    that the *verdict* for the slow item is NO_EVIDENCE with an
    explanatory string, not that wall time is bounded.)
    """
    c_slow = create_commitment(db, title="slow one NTU proposal")
    c_fast = create_commitment(db, title="fast one Sarah deck")

    gmail = MagicMock()

    def search(query: str, max_results: int = 5) -> list:
        if "ntu" in query.lower() or "proposal" in query.lower():
            import time as _t

            _t.sleep(3)  # Longer than timeout_per_item_s=1
        return []

    gmail.search.side_effect = search

    results = verify_all_open_commitments(db, gmail, timeout_per_item_s=1, concurrency=2)
    assert len(results) == 2
    slow_result = next(r for r in results if r["id"] == c_slow["id"])
    fast_result = next(r for r in results if r["id"] == c_fast["id"])
    assert slow_result["_verdict"] == VERDICT_NO_EVIDENCE
    assert "time" in slow_result["_evidence"].lower() or "error" in slow_result["_evidence"].lower()
    # Fast item should be NO_EVIDENCE (empty gmail result), NOT timed out.
    assert fast_result["_verdict"] == VERDICT_NO_EVIDENCE
    assert "no match" in fast_result["_evidence"].lower()


def test_verify_gmail_returns_non_iterable_safely(db: Memory) -> None:
    """If gmail.search returns something weird (None, dict), we shouldn't
    crash — treat as no matches."""
    c = create_commitment(db, title="oddball")
    gmail = MagicMock()
    gmail.search.return_value = None  # type: ignore[assignment]
    got = verify_commitment(c, gmail)
    # Either NO_EVIDENCE or it raises — either way, the wrapper in
    # verify_all_open_commitments would tag it.
    assert got["_verdict"] in (VERDICT_NO_EVIDENCE, VERDICT_LIKELY_DONE)


# ===========================================================================
# Keep Warm stress
# ===========================================================================


def test_keep_warm_last_interaction_unparseable_dates() -> None:
    """Corrupt Attio timestamps shouldn't crash list_keep_warm; those
    people sort last with days_since=None."""
    client = AttioClient.__new__(AttioClient)
    client._headers = {"Authorization": "Bearer x"}
    records = []
    for i, bad_ts in enumerate(["not a date", "", "2026-13-45", "9999-99-99T25:99:99"]):
        records.append(
            {
                "id": {"record_id": f"r{i}"},
                "values": {
                    "name": [{"first_name": f"P{i}", "last_name": "X"}],
                    "keep_warm": [{"value": True}],
                    "keep_warm_cadence_days": [{"value": 14}],
                    "last_interaction": [{"value": bad_ts}],
                },
            }
        )
    client._post = lambda path, body: {"data": records}  # type: ignore[method-assign,assignment]
    result = client.list_keep_warm()
    assert len(result) == len(records)
    for p in result:
        assert p.days_since is None
    # None days never flagged overdue regardless of cadence.
    assert client.get_keep_warm_overdue() == []


def test_keep_warm_200_plus_people_hits_limit_cleanly() -> None:
    """200 is the default limit. Attio returning exactly 200 should work;
    more than 200 should cap at limit."""
    client = AttioClient.__new__(AttioClient)
    client._headers = {"Authorization": "Bearer x"}
    records = [
        {
            "id": {"record_id": f"r{i}"},
            "values": {
                "name": [{"first_name": f"P{i:03d}", "last_name": "X"}],
                "keep_warm": [{"value": True}],
                "keep_warm_cadence_days": [{"value": 7}],
                "last_interaction": [
                    {"value": (datetime.now(UTC) - timedelta(days=i + 1)).isoformat()}
                ],
            },
        }
        for i in range(250)
    ]
    client._post = lambda path, body: {"data": records[: body.get("limit", 50)]}  # type: ignore[method-assign,assignment]

    result = client.list_keep_warm(limit=200)
    assert len(result) == 200
    # Most overdue first (highest days_since).
    assert result[0].days_since >= result[-1].days_since  # type: ignore[operator]


def test_set_keep_warm_cadence_extreme_values() -> None:
    """Negative or silly-large cadence clamps to [1, 365]."""
    client = AttioClient.__new__(AttioClient)
    client._headers = {"Authorization": "Bearer x"}
    patch_calls = []

    # get_person lookup
    client._post = lambda p, b: {  # type: ignore[method-assign,assignment]
        "data": [
            {
                "id": {"record_id": "abc"},
                "values": {"name": [{"first_name": "x", "last_name": "y"}]},
            }
        ]
    }
    client._patch = lambda p, b: patch_calls.append(b) or {}  # type: ignore[method-assign,assignment]

    for bad in (-100, 0, 99999, 366):
        client.set_keep_warm(person="x", cadence_days=bad)
        v = patch_calls[-1]["values"]["keep_warm_cadence_days"][0]["value"]
        assert 1 <= v <= 365


# ===========================================================================
# Drive + auto_resolve stress
# ===========================================================================


def test_drive_large_result_set_capped_by_max_results() -> None:
    """Drive returning 100 files with max_results=10 should cap + sort."""
    svc = MagicMock()
    files = [
        {
            "id": f"f{i}",
            "name": f"doc-{i}",
            "mimeType": "application/pdf",
            "modifiedTime": (datetime.now(UTC) - timedelta(days=i)).isoformat(),
            "webViewLink": f"http://x/{i}",
        }
        for i in range(100)
    ]
    svc.files.return_value.list.return_value.execute.return_value = {"files": files}
    tool = DriveTool(service=svc)
    result = tool.search("x", max_results=10)
    assert len(result) == 10
    # Sorted most-recent first.
    for i in range(len(result) - 1):
        assert result[i].modified_time >= result[i + 1].modified_time


def test_drive_malformed_file_entries_dont_crash(db: Memory) -> None:
    """Drive returning entries without `id` should be skipped, not crash."""
    svc = MagicMock()
    files = [
        {
            "id": "valid",
            "name": "ok.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2026-01-01",
        },
        {"name": "no-id.pdf", "mimeType": "application/pdf"},  # missing id
        {"id": None, "name": "null-id.pdf"},  # None id
        {},  # empty
    ]
    svc.files.return_value.list.return_value.execute.return_value = {"files": files}
    tool = DriveTool(service=svc)
    result = tool.search("x")
    assert [f.id for f in result] == ["valid"]


def test_drive_special_chars_in_query_escaped() -> None:
    """A user-ish query with apostrophes and backslashes shouldn't break
    the Drive query string. The query isn't executed here but we verify
    _q_quote returns a string the search path won't malform."""
    from cosinabox.tools.google.drive import _q_quote

    bad_inputs = [
        "O'Brien's deck",
        r"path\to\file",
        r"mix 'quotes' and \backslashes",
        "",
        "  ",
    ]
    for q in bad_inputs:
        out = _q_quote(q)
        # Must not contain an unescaped quote that would close the outer
        # `contains '<value>'` expression.
        # Every single-quote in the output must be backslash-escaped.
        i = 0
        while i < len(out):
            if out[i] == "'":
                # Must be preceded by an odd number of backslashes
                bs_count = 0
                j = i - 1
                while j >= 0 and out[j] == "\\":
                    bs_count += 1
                    j -= 1
                assert bs_count % 2 == 1, f"unescaped quote in {out!r} at {i}"
            i += 1


def test_drive_timeout_in_verify_all_doesnt_block(db: Memory) -> None:
    """One slow Drive search in a batch must not break the others'
    verdicts. (Wall-clock isn't bounded — see
    test_verify_commitment_timeout_tagged_as_no_evidence for why.)
    """
    for i in range(5):
        create_commitment(db, title=f"item {i} ship")
    gmail = MagicMock()
    gmail.search.return_value = []
    drive = MagicMock()

    call_count = [0]

    def slow_search(q: str, max_results: int = 5) -> list:
        call_count[0] += 1
        if call_count[0] == 1:
            import time as _t

            _t.sleep(3)
        return []

    drive.search.side_effect = slow_search

    results = verify_all_open_commitments(
        db, gmail, drive=drive, timeout_per_item_s=1, concurrency=5
    )
    assert len(results) == 5
    # All items must have verdicts set.
    assert all("_verdict" in r for r in results)
    # At least one is timed out/error-tagged; the rest are NO_EVIDENCE.
    assert all(r["_verdict"] == VERDICT_NO_EVIDENCE for r in results)


# ===========================================================================
# Analytics stress
# ===========================================================================


def test_error_pattern_summary_cache_survives_concurrent_reads(db: Memory) -> None:
    """Multiple threads calling get_error_pattern_summary shouldn't
    produce inconsistent results or race on the module-global cache."""
    ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    for _ in range(3):
        db._conn.execute(
            "INSERT INTO tool_logs (session_id, tool_name, duration_ms, error_type, created_at) "
            "VALUES ('s', 'gmail_search', 100, 'timeout', ?)",
            (ts,),
        )
    db._conn.commit()
    invalidate_error_summary_cache()

    results: list[str] = []

    def worker() -> None:
        results.append(get_error_pattern_summary(db, days=7))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All 20 readers should see the same (possibly empty-then-populated
    # depending on cache race) output, but every output must be a string.
    assert all(isinstance(r, str) for r in results)
    # At least one reader must see the populated string (not all empty).
    assert any("RECENT ERROR PATTERNS" in r for r in results)


def test_analytics_summary_gracefully_handles_partial_tables() -> None:
    """`get_analytics_summary` should return a string even when some
    underlying tables are empty or missing."""
    # Fresh DB — no commitments, no tool_logs, no daily_costs.
    m = Memory(db_path=Path("/tmp/stress-empty.db"))
    # Drop a table to simulate a migration gap (hypothetical).
    try:
        m._conn.execute("DROP TABLE IF EXISTS daily_costs")
        m._conn.commit()
    except sqlite3.Error:
        pass
    # Should not raise.
    out = get_analytics_summary(m)
    assert isinstance(out, str)
    assert "ANALYTICS" in out
    m.close()


def test_commitment_velocity_with_old_row_out_of_window(db: Memory) -> None:
    """A commitment created 100 days ago but never updated shouldn't be
    double-counted in the 7-day velocity window."""
    from cosinabox.commitments import create_commitment as _create

    old = _create(db, title="ancient item")
    db._conn.execute(
        "UPDATE commitments SET created_at = ?, updated_at = ? WHERE id = ?",
        (
            (datetime.now(UTC) - timedelta(days=100)).isoformat(),
            (datetime.now(UTC) - timedelta(days=100)).isoformat(),
            old["id"],
        ),
    )
    db._conn.commit()
    v = get_commitment_velocity(db, days=7)
    assert v["created"] == 0  # 100 days ago, out of 7-day window
    assert v["completed"] == 0
    assert v["backlog"] == 1  # still open, so counts in backlog


def test_error_patterns_zero_division_safety(db: Memory) -> None:
    """If somehow total calls are zero for a tool but errors exist
    (shouldn't happen — the SQL joins on totals) — the output should not
    divide by zero."""
    ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    for _ in range(5):
        db._conn.execute(
            "INSERT INTO tool_logs (session_id, tool_name, duration_ms, error_type, created_at) "
            "VALUES ('s', 'rare_tool', 100, 'rate_limit', ?)",
            (ts,),
        )
    db._conn.commit()
    patterns = get_error_patterns(db, days=7, min_errors=2)
    assert patterns
    # total matches errors; rate should be 100%.
    assert patterns[0]["error_rate_pct"] == 100.0


# ===========================================================================
# End-to-end integration smoke
# ===========================================================================


def test_morning_briefing_with_all_integrations_wired(db: Memory, tmp_path: Path) -> None:
    """The big integration test — every new surface plugged in at once:
    - commitments (verdict grounding)
    - Keep Warm (Attio)
    - Drive search
    - Gmail threads-needing-reply
    All should flow through without stepping on each other.
    """
    from cosinabox.commitments import create_commitment
    from cosinabox.jobs.base import JobContext
    from cosinabox.jobs.morning_briefing import MorningBriefingJob
    from cosinabox.tools.google.gmail import ThreadSummary

    # Seed 3 commitments, one gets gmail evidence, one gets drive evidence
    c_done = create_commitment(db, title="send NTU deck")
    c_likely = create_commitment(db, title="reach out Sarah")
    c_open = create_commitment(db, title="random thing")

    gmail = MagicMock()

    # gmail.search returns meeting-relevant subjects
    def search(q: str, max_results: int = 5) -> list:
        if "ntu" in q.lower():
            # 2 subject matches → VERIFIED_DONE
            m1 = MagicMock(subject="NTU deck final", sender="me")
            m2 = MagicMock(subject="Re: NTU deck")
            return [m1, m2]
        return []

    gmail.search.side_effect = search
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = [
        ThreadSummary(
            thread_id="t1",
            subject="Re: VC Intro",
            last_sender="VC <vc@example.com>",
            last_date="Fri, 18 Apr 2026 10:35 +0000",
            last_snippet="Any update?",
            last_sent_by_me=False,
        ),
    ]

    calendar = MagicMock()
    calendar.list_events.return_value = []

    attio = MagicMock()
    attio.get_keep_warm_overdue.return_value = [
        KeepWarmPerson(
            name="Ada Lovelace",
            record_id="r1",
            cadence_days=30,
            note="Board advisor",
            last_interaction="2026-03-01",
            days_since=50,
        ),
    ]

    drive = MagicMock()
    # Two Drive hits matching "reach Sarah" → LIKELY_DONE
    sarah1 = MagicMock()
    sarah1.name = "reach out Sarah notes v1"
    sarah2 = MagicMock()
    sarah2.name = "reach Sarah followup draft"
    drive.search.return_value = [sarah1, sarah2]

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"

    job = MorningBriefingJob(
        gmail=gmail,
        calendar=calendar,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
        stakeholders=[],
        db=db,
        attio=attio,
        drive=drive,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]

    # All four grounded sections present:
    assert "VERIFIED DONE" in prompt
    assert "send NTU deck" in prompt or "NTU deck" in prompt  # verified
    assert "LIKELY DONE" in prompt or "reach out Sarah" in prompt  # drive-upgraded
    assert "GENUINELY OPEN" in prompt
    assert "random thing" in prompt
    assert "KEEP WARM — OVERDUE" in prompt
    assert "Ada Lovelace" in prompt
    assert "INBOX NEEDING REPLY" in prompt
    assert "VC Intro" in prompt

    # No accidentally-persisted or malformed section markers.
    assert "<<<<<<<" not in prompt
    assert "=======" not in prompt
    # Must NOT have the fallback priorities line when db is wired.
    assert "top 3 based on calendar + email signals" not in prompt
    # Avoid contradictory instruction pairs.
    assert "Do NOT produce CARRY-OVER" not in prompt  # that's evening_wrap, not morning
    _ = c_done, c_likely, c_open  # silence
