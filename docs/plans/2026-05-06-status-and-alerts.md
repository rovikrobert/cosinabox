# Plan: `/status` per-account auth + alert enrichment (Initiative C)

> **For agentic workers:** Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md`, "Initiative C".
**Sequencing:** Initiative B must merge first (this plan does not depend on B's check class but the spec orders A→B→C; do B's PR first to keep the retro chain clean).
**Branch:** `feat/status-oauth-line` at `~/.worktrees/cosinabox/feat-status-oauth-line` (created at execution time).
**How to resume:** open this file, find the first `- [ ]` checkbox, follow the milestone's steps. Plan is self-contained.

## Goal

Make per-account OAuth health observable in two surfaces: `/status` (the user can ask for it) and the existing `auth_health` Telegram alerts (the bot pushes it). Both surfaces should reference `cosinabox auth refresh` as the single fix command — no more "auth google + paste + redeploy" two-step in any user-facing string.

## Architecture

- **Persistence**: new `auth_health_status` table inside the existing `<config_dir>/.cosinabox/memory.db`. One row per account index. Schema: `(account_index INT PRIMARY KEY, email TEXT, last_status TEXT, last_check_at TEXT)`.
- **Writer**: `AuthHealthJob.run()` writes one row per credential per tick (after the existing in-memory transition logic). Transient errors (`TransportError`, etc.) do not write — preserve the prior row, same semantic as the in-memory `_health` dict today.
- **Reader**: a small helper `read_auth_health(db_path) -> list[dict]` consumed by `/status`.
- **`/status` rendering**: append a single OAuth line *only when the table has rows* (omit on fresh deploys before auth_health has ticked). Single-account users see the line too — uniformity beats hiding it.
- **Alert enrichment**: replace the multi-step `Run: cosinabox auth google, update GOOGLE_OAUTH_REFRESH_TOKEN_<N> on Railway, redeploy.` with a single line `Run: cosinabox auth refresh`. Update both surfaces (`_runtime_alert.py` for live failures during job runs, `jobs/auth_health.py:_FAILURE_TEMPLATE` for the proactive watcher).

## Tech Stack

Python 3.11+, stdlib `sqlite3`, existing `_runtime_alert.py` + `auth_health.py` patterns. Tests use `tmp_path` fixtures with a real on-disk SQLite file (no mocking the DB layer — it's stdlib, fast, and the test exercise is real).

## Files

| Path | Action | Responsibility |
|---|---|---|
| `src/cosinabox/jobs/auth_health.py` | Modify | Add persistence write per tick + update `_FAILURE_TEMPLATE`. New optional `db_path` arg on `AuthHealthJob.__init__`. |
| `src/cosinabox/jobs/auth_health_persist.py` | Create | `AUTH_HEALTH_SCHEMA` + `record_auth_health()` + `read_auth_health()`. Standalone module so `/status` can import without dragging in the job class. |
| `src/cosinabox/tools/google/_runtime_alert.py` | Modify | Update the live-failure alert string to end with `Run: cosinabox auth refresh`. |
| `src/cosinabox/bot/commands.py` | Modify | `build_status_handler` reads `auth_health_status`; appends OAuth line when rows exist. |
| `src/cosinabox/app/_core.py` (or `app/jobs.py`) | Modify | Pass the user-repo's `memory.db` path into `AuthHealthJob` and `build_status_handler`. |
| `tests/unit/test_auth_health_persist.py` | Create | DB schema + CRUD tests. |
| `tests/unit/test_jobs_auth_health.py` | Modify | Assert that `run()` writes rows when `db_path` is provided. |
| `tests/unit/test_bot_commands.py` | Modify | Assert `/status` renders the OAuth line when rows exist; omits when empty. |
| `tests/unit/test_runtime_oauth_alert.py` | Modify | Assert the new `auth refresh` line appears. |

---

## M1 — Open questions sign-off

Five open questions surfaced and signed off in chat (2026-05-06):

| Q | Decision |
|---|---|
| Storage | Same `memory.db`; new `auth_health_status` table |
| Schema | `(account_index INT PRIMARY KEY, email TEXT, last_status TEXT, last_check_at TEXT)`; statuses `'ok' | 'failed'`; transient errors do NOT write |
| /status for single-account | Yes — uniformity beats hiding |
| Empty state | Omit OAuth line when no rows (don't show "(unknown)") |
| Alerts | Update both `_runtime_alert.py` and `jobs/auth_health.py` to `Run: cosinabox auth refresh` |

- [x] **Sign-off received in chat.** Proceed to M2.

**Estimate:** 0 (already done).

---

## M2 — Persistence module (schema + CRUD)

**Files:**
- Create: `src/cosinabox/jobs/auth_health_persist.py`
- Create: `tests/unit/test_auth_health_persist.py`

### Steps

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_auth_health_persist.py`

```python
"""Tests for the auth_health_status persistence layer.

Uses a real on-disk SQLite file (sqlite3 is stdlib, fast). No mocking
the DB — the layer's whole purpose is talking to it correctly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cosinabox.jobs.auth_health_persist import (
    AUTH_HEALTH_SCHEMA,
    read_auth_health,
    record_auth_health,
)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(AUTH_HEALTH_SCHEMA)
    return conn


def test_record_then_read_returns_row(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=True)
    rows = read_auth_health(db)
    assert len(rows) == 1
    assert rows[0]["account_index"] == 1
    assert rows[0]["email"] == "rovik@example.com"
    assert rows[0]["last_status"] == "ok"
    assert rows[0]["last_check_at"]  # ISO timestamp


def test_record_upserts_on_account_index(tmp_path: Path) -> None:
    """Writing twice for the same account_index updates, doesn't insert."""
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=True)
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=False)
    rows = read_auth_health(db)
    assert len(rows) == 1
    assert rows[0]["last_status"] == "failed"


def test_record_multiple_accounts(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="a@example.com", ok=True)
    record_auth_health(db, account_index=2, email="b@example.com", ok=False)
    rows = read_auth_health(db)
    assert len(rows) == 2
    by_idx = {r["account_index"]: r for r in rows}
    assert by_idx[1]["last_status"] == "ok"
    assert by_idx[2]["last_status"] == "failed"


def test_read_returns_empty_list_when_table_empty(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    # Don't write anything; just create the schema.
    _connect(db).close()
    assert read_auth_health(db) == []


def test_read_returns_empty_list_when_db_missing(tmp_path: Path) -> None:
    """A fresh user-repo with no memory.db yet should return [], not crash."""
    db = tmp_path / "does-not-exist.db"
    assert read_auth_health(db) == []


def test_schema_is_idempotent(tmp_path: Path) -> None:
    """Creating the schema twice (e.g., on app restart) must not error."""
    db = tmp_path / "memory.db"
    _connect(db).close()
    # Second call should be a no-op.
    _connect(db).close()


def test_rows_ordered_by_account_index(tmp_path: Path) -> None:
    """read_auth_health sorts by account_index so /status renders 1, 2, 3 in order."""
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=3, email="c@example.com", ok=True)
    record_auth_health(db, account_index=1, email="a@example.com", ok=True)
    record_auth_health(db, account_index=2, email="b@example.com", ok=False)
    rows = read_auth_health(db)
    assert [r["account_index"] for r in rows] == [1, 2, 3]
```

- [ ] **Step 2: Run to confirm fails**

```bash
.venv/bin/pytest tests/unit/test_auth_health_persist.py -v
```

Expected: `ModuleNotFoundError: cosinabox.jobs.auth_health_persist`.

- [ ] **Step 3: Implement** in `src/cosinabox/jobs/auth_health_persist.py`

```python
"""Persistence for `auth_health` per-account state.

The auth_health watcher (jobs/auth_health.py) maintains an in-memory
dict of per-account refresh-token health. That state is per-process
and disappears on restart. This module persists it to the user repo's
``memory.db`` so:

  - `/status` can read the latest health without waiting for the next
    auth_health tick.
  - A bot restart doesn't lose the prior known state.

Schema is intentionally minimal: one row per account index,
last-known status only. No history; the auth_health alerts already
capture transitions.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTH_HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_health_status (
    account_index INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    last_status TEXT NOT NULL,
    last_check_at TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection and ensure the schema exists. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(AUTH_HEALTH_SCHEMA)
    conn.commit()
    return conn


def record_auth_health(
    db_path: Path, *, account_index: int, email: str, ok: bool
) -> None:
    """Insert or update the per-account auth health row.

    Status is the literal string ``'ok'`` or ``'failed'`` (no transient
    state — callers should skip writing on transient errors so the prior
    row is preserved).
    """
    status = "ok" if ok else "failed"
    now = datetime.now(UTC).isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO auth_health_status (account_index, email, last_status, last_check_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_index) DO UPDATE SET
                email = excluded.email,
                last_status = excluded.last_status,
                last_check_at = excluded.last_check_at
            """,
            (account_index, email, status, now),
        )
        conn.commit()
    finally:
        conn.close()


def read_auth_health(db_path: Path) -> list[dict[str, Any]]:
    """Return all per-account health rows, ordered by account_index.

    Returns ``[]`` if the DB file doesn't exist yet (fresh user-repo
    before auth_health has ticked) — callers should treat empty as
    "no data, hide the row" rather than "(unknown)".
    """
    if not db_path.exists():
        return []
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT account_index, email, last_status, last_check_at "
            "FROM auth_health_status ORDER BY account_index"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests, confirm green**

```bash
.venv/bin/pytest tests/unit/test_auth_health_persist.py -v
```

Expected: 7 pass.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/jobs/auth_health_persist.py tests/unit/test_auth_health_persist.py
git commit -m "feat(auth-health): SQLite persistence for per-account status

Plan: 2026-05-06-status-and-alerts, M2.
New auth_health_status table in memory.db with primary key on
account_index. record_auth_health upserts; read_auth_health returns
ordered rows or [] when the DB doesn't exist yet (fresh user-repo).

Standalone module so /status can read without importing the job
class."
```

**Estimate:** 30 min.

---

## M3 — Wire `AuthHealthJob` to persist + update `_FAILURE_TEMPLATE`

**Files:**
- Modify: `src/cosinabox/jobs/auth_health.py`
- Modify: `tests/unit/test_jobs_auth_health.py`

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_jobs_auth_health.py`)

```python
def test_run_persists_per_account_status(tmp_path: Path) -> None:
    """When db_path is provided, run() writes one row per credential per tick."""
    from unittest.mock import MagicMock

    from cosinabox.jobs.auth_health import AuthHealthJob, JobContext
    from cosinabox.jobs.auth_health_persist import read_auth_health

    db = tmp_path / "memory.db"

    healthy = MagicMock()
    healthy.refresh = MagicMock(return_value=None)
    dead = MagicMock()
    from google.auth.exceptions import RefreshError

    dead.refresh = MagicMock(side_effect=RefreshError("revoked"))

    job = AuthHealthJob(
        credentials_factory=lambda: [healthy, dead],
        db_path=db,
        account_emails=["ok@example.com", "dead@example.com"],
    )
    job.run(JobContext())

    rows = read_auth_health(db)
    assert len(rows) == 2
    by_idx = {r["account_index"]: r for r in rows}
    assert by_idx[1]["last_status"] == "ok"
    assert by_idx[1]["email"] == "ok@example.com"
    assert by_idx[2]["last_status"] == "failed"
    assert by_idx[2]["email"] == "dead@example.com"


def test_run_does_not_persist_on_transient_error(tmp_path: Path) -> None:
    """Transient errors (TransportError) must NOT overwrite the prior row.

    The whole point of the in-memory _health-skip-on-transient logic is
    not panicking when the network blips. Persistence must mirror that.
    """
    from unittest.mock import MagicMock

    from cosinabox.jobs.auth_health import AuthHealthJob, JobContext
    from cosinabox.jobs.auth_health_persist import read_auth_health, record_auth_health

    db = tmp_path / "memory.db"
    # Seed a known-good row.
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=True)

    from google.auth.exceptions import TransportError

    cred = MagicMock()
    cred.refresh = MagicMock(side_effect=TransportError("connection reset"))

    job = AuthHealthJob(
        credentials_factory=lambda: [cred],
        db_path=db,
        account_emails=["rovik@example.com"],
    )
    job.run(JobContext())

    rows = read_auth_health(db)
    assert len(rows) == 1
    # Status preserved as "ok" — transient error didn't flip it.
    assert rows[0]["last_status"] == "ok"


def test_run_without_db_path_does_not_crash() -> None:
    """Backwards compat: existing callers that don't pass db_path must
    still work (just no persistence)."""
    from unittest.mock import MagicMock

    from cosinabox.jobs.auth_health import AuthHealthJob, JobContext

    cred = MagicMock()
    cred.refresh = MagicMock(return_value=None)

    job = AuthHealthJob(credentials_factory=lambda: [cred])
    # Just shouldn't raise.
    job.run(JobContext())


def test_failure_template_uses_auth_refresh() -> None:
    """The alert message users see must point at `cosinabox auth refresh`,
    NOT the legacy 'auth google + update token + redeploy' three-step.
    """
    from cosinabox.jobs.auth_health import _FAILURE_TEMPLATE

    msg = _FAILURE_TEMPLATE.format(i=2)
    assert "cosinabox auth refresh" in msg
    # Old multi-step phrasing must be gone.
    assert "update GOOGLE_OAUTH_REFRESH_TOKEN" not in msg
    assert "redeploy" not in msg.lower()
```

- [ ] **Step 2: Run, confirm fails**

```bash
.venv/bin/pytest tests/unit/test_jobs_auth_health.py -v
```

Expected: 4 new tests fail (db_path param doesn't exist; template still has old text).

- [ ] **Step 3: Edit `src/cosinabox/jobs/auth_health.py`**

Replace `_FAILURE_TEMPLATE` and extend `__init__` + `run`:

```python
"""Auth-health watcher — flag revoked Google refresh tokens before they're noticed by a human.

[existing docstring kept; only the body below changes]
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.tools.google.auth import GoogleAuthError, build_all_credentials

logger = logging.getLogger("cosinabox")

# After Initiative A (cosinabox auth refresh) shipped in v0.1.6, the fix
# instruction collapses from a three-step manual flow to a single command.
# Surfaces that referenced the old "auth google + update token + redeploy"
# pattern were updated in lockstep with this change.
_FAILURE_TEMPLATE = (
    "Google auth failed for account #{i}.\n"
    "Gmail and Calendar reads will be silently skipped until re-auth.\n"
    "Run: cosinabox auth refresh"
)
_RECOVERY_TEMPLATE = "Google auth restored for account #{i}."


class AuthHealthJob(Job):
    name = "auth_health"

    def __init__(
        self,
        *,
        credentials_factory: Callable[[], Iterable[Any]] = build_all_credentials,
        db_path: Path | None = None,
        account_emails: list[str] | None = None,
    ) -> None:
        """Args:
            credentials_factory: callable returning the list of Credentials
                to probe each tick. Defaults to build_all_credentials().
            db_path: path to the user repo's memory.db. When provided,
                each tick persists per-account status to the
                auth_health_status table for /status to read. Optional
                so existing callers (and tests) don't need to thread it.
            account_emails: ordered list of emails matching the
                credentials returned by the factory. Used as the email
                field in persisted rows. When None, falls back to
                "(unknown)" so persistence still works.
        """
        self.credentials_factory = credentials_factory
        self.db_path = db_path
        self.account_emails = list(account_emails or [])
        self._health: dict[int, bool] = {}

    def run(self, context: JobContext) -> str:
        try:
            creds = list(self.credentials_factory())
        except GoogleAuthError:
            return ""

        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request

        request = Request()
        newly_failed: list[str] = []
        newly_recovered: list[str] = []

        for i, cred in enumerate(creds, start=1):
            ok: bool
            try:
                cred.refresh(request)
                ok = True
            except RefreshError as exc:
                logger.warning("Auth-health: account #%d refresh failed: %s", i, exc)
                ok = False
            except Exception as exc:  # noqa: BLE001 — preserve state on transient failures
                logger.warning(
                    "Auth-health: account #%d raised %s; keeping prior state",
                    i,
                    type(exc).__name__,
                )
                continue

            prev = self._health.get(i)
            if ok is False and prev is not False:
                newly_failed.append(_FAILURE_TEMPLATE.format(i=i))
            elif ok is True and prev is False:
                newly_recovered.append(_RECOVERY_TEMPLATE.format(i=i))
            self._health[i] = ok

            # Persist (skipped on transient errors via the `continue` above).
            if self.db_path is not None:
                from cosinabox.jobs.auth_health_persist import record_auth_health

                email = (
                    self.account_emails[i - 1]
                    if 0 < i <= len(self.account_emails)
                    else "(unknown)"
                )
                try:
                    record_auth_health(
                        self.db_path, account_index=i, email=email, ok=ok
                    )
                except Exception:  # noqa: BLE001 — persistence must never break the watcher
                    logger.warning(
                        "Auth-health: failed to persist account #%d state", i, exc_info=True
                    )

        sections: list[str] = []
        if newly_failed:
            sections.append("\n".join(newly_failed))
        if newly_recovered:
            sections.append("\n".join(newly_recovered))
        return "\n\n".join(sections)
```

- [ ] **Step 4: Run, confirm green**

```bash
.venv/bin/pytest tests/unit/test_jobs_auth_health.py -v
```

Expected: all green (existing + 4 new).

- [ ] **Step 5: Wire `db_path` and `account_emails` from app/_core.py**

Read `src/cosinabox/app/_core.py` around the existing `set_account_emails(...)` call (line ~340 per current main). The same `google_accounts` list provides the emails for `AuthHealthJob`. The same `memory.db` path is used by `Memory(db_path=...)` already.

Find where `AuthHealthJob` is constructed/registered. (Per Plan 4 of the auth-health watcher, registration lives in `src/cosinabox/app/jobs.py:register_core_jobs`.) Edit that registration site to pass:

```python
auth_health_cfg = jobs_config.get("auth_health", {})
if auth_health_cfg.get("enabled", True):
    cron = auth_health_cfg.get("schedule", defaults.AUTH_HEALTH_DEFAULT_SCHEDULE)
    db_path = config_dir / ".cosinabox" / "memory.db"
    account_emails = [
        str(a["email"])
        for a in (integrations.get("google", {}).get("accounts") or [])
        if isinstance(a, dict) and a.get("email")
    ]
    scheduler.add_job(
        AuthHealthJob(db_path=db_path, account_emails=account_emails),
        cron=cron,
    )
```

The exact lines depend on the current shape of `register_core_jobs` (which signatures are passed in). If `config_dir` and `integrations` aren't already in scope, thread them in — both are already available at the App level, just not necessarily at this call site. Make the smallest threading change that compiles.

- [ ] **Step 6: Run the full unit suite**

```bash
.venv/bin/pytest tests/unit/ -q
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/cosinabox/jobs/auth_health.py src/cosinabox/app/jobs.py tests/unit/test_jobs_auth_health.py
git commit -m "feat(auth-health): persist per-account status + use auth refresh in alerts

Plan: 2026-05-06-status-and-alerts, M3.
- AuthHealthJob writes per-account state to memory.db each tick when
  db_path is provided; transient errors skip the write so prior known
  state is preserved.
- _FAILURE_TEMPLATE now ends with 'Run: cosinabox auth refresh'
  instead of the legacy three-step (auth google + update env var on
  Railway + redeploy). Initiative A's command absorbs all three.
- Wired db_path + account_emails through register_core_jobs."
```

**Estimate:** 45 min.

---

## M4 — Update `_runtime_alert.py` to point at `auth refresh`

**Files:**
- Modify: `src/cosinabox/tools/google/_runtime_alert.py`
- Modify: `tests/unit/test_runtime_oauth_alert.py`

### Steps

- [ ] **Step 1: Read `src/cosinabox/tools/google/_runtime_alert.py`** (whole file is ~70 lines).

- [ ] **Step 2: Append the test** in `tests/unit/test_runtime_oauth_alert.py`

```python
def test_alert_message_points_at_auth_refresh() -> None:
    """Live OAuth-failure alerts must instruct the user to run
    `cosinabox auth refresh` (Initiative A's command), not the legacy
    multi-step manual flow.
    """
    from unittest.mock import MagicMock

    from cosinabox.tools.google._runtime_alert import (
        emit_runtime_oauth_alert,
        set_account_emails,
        set_send_telegram,
    )

    sent: list[str] = []
    set_send_telegram(lambda msg: sent.append(msg))
    set_account_emails(["rovik@example.com", "rovik@cantina.ai"])

    emit_runtime_oauth_alert(account_index=2, error=RuntimeError("revoked"))

    assert len(sent) == 1
    assert "rovik@cantina.ai" in sent[0]
    assert "cosinabox auth refresh" in sent[0]
```

(Adjust the imports / function names to match the real `_runtime_alert.py` API. The intent of the assertion is what matters: the new fix string must appear, the old multi-step must not.)

- [ ] **Step 3: Run, confirm fails**

```bash
.venv/bin/pytest tests/unit/test_runtime_oauth_alert.py -v
```

Expected: assertion fails — the existing message doesn't say `auth refresh` yet.

- [ ] **Step 4: Edit `src/cosinabox/tools/google/_runtime_alert.py`** — change the alert template string so it ends with `Run: cosinabox auth refresh`. Mirror the wording in `auth_health.py:_FAILURE_TEMPLATE` for consistency.

- [ ] **Step 5: Run tests + lint + types.**

- [ ] **Step 6: Commit.**

```bash
git add src/cosinabox/tools/google/_runtime_alert.py tests/unit/test_runtime_oauth_alert.py
git commit -m "refactor(runtime-alert): live OAuth alerts use 'cosinabox auth refresh'

Plan: 2026-05-06-status-and-alerts, M4.
The runtime alert path (token expired during a job run, not via
auth_health watcher) now uses the same single-command fix string as
auth_health. Prior text walked the user through the legacy three-step
manual flow; that was the symptom Initiative A removed."
```

**Estimate:** 20 min.

---

## M5 — `/status` reads and renders OAuth line

**Files:**
- Modify: `src/cosinabox/bot/commands.py`
- Modify: `src/cosinabox/app/_core.py` (thread `db_path` into `build_status_handler`)
- Modify: `tests/unit/test_bot_commands.py`

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_bot_commands.py`)

```python
def test_status_renders_oauth_line_when_rows_exist(tmp_path: Path) -> None:
    """When auth_health has persisted rows, /status appends:
        OAuth: ✓ <healthy-email> | ✗ <dead-email>
    """
    from unittest.mock import MagicMock

    from cosinabox.bot.commands import build_status_handler
    from cosinabox.jobs.auth_health_persist import record_auth_health

    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@majiq.agency", ok=True)
    record_auth_health(db, account_index=2, email="rovik@cantina.ai", ok=False)

    handler = build_status_handler(
        name="Rovik",
        timezone="Asia/Singapore",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )

    update = MagicMock()
    update.message = MagicMock()
    sent: list[str] = []
    update.message.reply_text = (
        lambda txt: sent.append(txt) or _async_nothing()
    )

    import asyncio

    async def _async_nothing():
        return None

    asyncio.run(handler(update, None))

    text = sent[0]
    assert "OAuth:" in text
    assert "rovik@majiq.agency" in text
    assert "rovik@cantina.ai" in text
    # Status indicators present.
    assert "✓" in text
    assert "✗" in text


def test_status_omits_oauth_line_when_empty(tmp_path: Path) -> None:
    """No persisted rows → no OAuth line. Don't show '(unknown)' noise."""
    import asyncio
    from unittest.mock import MagicMock

    from cosinabox.bot.commands import build_status_handler

    db = tmp_path / "memory.db"  # File doesn't exist; persisted state empty.

    handler = build_status_handler(
        name="x",
        timezone="UTC",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )

    update = MagicMock()
    update.message = MagicMock()
    sent: list[str] = []

    async def _reply(text):
        sent.append(text)

    update.message.reply_text = _reply
    asyncio.run(handler(update, None))

    assert "OAuth:" not in sent[0]


def test_status_renders_oauth_line_for_single_account(tmp_path: Path) -> None:
    """Single-account users see the OAuth line too — uniformity beats
    hiding the row (spec open question #2)."""
    import asyncio
    from unittest.mock import MagicMock

    from cosinabox.bot.commands import build_status_handler
    from cosinabox.jobs.auth_health_persist import record_auth_health

    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="solo@example.com", ok=True)

    handler = build_status_handler(
        name="x",
        timezone="UTC",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )

    update = MagicMock()
    update.message = MagicMock()
    sent: list[str] = []

    async def _reply(text):
        sent.append(text)

    update.message.reply_text = _reply
    asyncio.run(handler(update, None))

    assert "OAuth:" in sent[0]
    assert "solo@example.com" in sent[0]
```

- [ ] **Step 2: Run, confirm fails** (`build_status_handler` doesn't accept `db_path` yet).

- [ ] **Step 3: Edit `src/cosinabox/bot/commands.py`** — add `db_path` kwarg to `build_status_handler` and append the OAuth line:

```python
def build_status_handler(
    *,
    name: str,
    timezone: str,
    tool_definitions: list[dict[str, Any]],
    jobs_config: dict[str, Any],
    stakeholder_count: int,
    db_path: Path | None = None,
) -> Any:
    """Build a /status handler with baked-in config context.

    When ``db_path`` is provided and the auth_health watcher has written
    rows, the response includes an extra `OAuth:` line summarising
    per-account status. Hidden when no rows exist (fresh deploy).
    """

    async def cmd_status(update: Update, _ctx: Any) -> None:
        enabled_jobs = [k for k, v in jobs_config.items() if v.get("enabled")]
        tool_names = [d["name"] for d in tool_definitions]

        lines = [
            f"Name: {name}",
            f"Timezone: {timezone}",
            f"Tools: {len(tool_names)} ({', '.join(tool_names) or 'none'})",
            f"Jobs: {', '.join(enabled_jobs) or 'none'}",
            f"Stakeholders: {stakeholder_count}",
        ]

        if db_path is not None:
            from cosinabox.jobs.auth_health_persist import read_auth_health

            rows = read_auth_health(db_path)
            if rows:
                parts = [
                    f"{'✓' if r['last_status'] == 'ok' else '✗'} {r['email']}"
                    for r in rows
                ]
                lines.append(f"OAuth: {' | '.join(parts)}")

        if update.message:
            await update.message.reply_text("\n".join(lines))

    return cmd_status
```

- [ ] **Step 4: Thread `db_path` into the call site** in `src/cosinabox/app/_core.py`. Find the `build_status_handler(...)` call (Telegram registration block) and add `db_path=self.config_dir / ".cosinabox" / "memory.db"`.

- [ ] **Step 5: Run tests, full suite, lint, mypy.**

- [ ] **Step 6: Commit.**

```bash
git add src/cosinabox/bot/commands.py src/cosinabox/app/_core.py tests/unit/test_bot_commands.py
git commit -m "feat(status): per-account OAuth health line in /status response

Plan: 2026-05-06-status-and-alerts, M5.
Reads the auth_health_status table written by AuthHealthJob and
appends a single 'OAuth: ✓ <email> | ✗ <email>' line. Hidden on fresh
deploys (no rows yet) — uniformity for empty state would be noise.
Single-account users see the line too: spec open question #2."
```

**Estimate:** 30 min.

---

## M6 — PR + retro

### Steps

- [ ] **Step 1: Final pre-PR check.**

```bash
.venv/bin/pytest tests/ -q
.venv/bin/ruff check src tests
.venv/bin/mypy src/cosinabox
```

- [ ] **Step 2: Push the branch.**

```bash
git push -u origin feat/status-oauth-line
```

- [ ] **Step 3: Open the PR.**

```bash
gh pr create \
  --title "feat: /status OAuth line + alert enrichment (Initiative C)" \
  --body "$(cat <<'EOF'
## Summary
- New `auth_health_status` table in `memory.db` persists per-account refresh-token health (PK on account_index, ok|failed status, ISO timestamp).
- `AuthHealthJob.run()` writes one row per credential per tick (transient errors skip the write so prior known state is preserved).
- `/status` appends `OAuth: ✓ rovik@majiq.agency | ✗ rovik@cantina.ai` when rows exist; hidden on fresh deploys.
- Both `_runtime_alert.py` and `auth_health.py` failure templates now end with `Run: cosinabox auth refresh` — collapses the legacy three-step (auth google + update env var + redeploy) into one command.

Initiative C of `docs/specs/2026-05-06-oauth-ux-rework.md`. Plan: `docs/plans/2026-05-06-status-and-alerts.md`.

## Test plan
- [x] Unit: persistence (7 tests), AuthHealthJob persistence (4 tests), runtime alert template (1 test), /status rendering (3 tests).
- [x] Full unit suite green.
- [x] Lint + types clean.
- [ ] **Maintainer manual smoke (optional but recommended):** wait for the next `auth_health` tick on `rovik-keevs`, then send `/status` to the bot. Verify the OAuth line shows the expected ✓/✗ for each account, and that any failure alert in Telegram now includes the `cosinabox auth refresh` line.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Auto-merge.**

```bash
gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 5: Retro** at `docs/retros/2026-05-06-status-and-alerts-retro.md`. Cover what shipped, estimate calibration, any surprises.

- [ ] **Step 6: Commit retro on `main` after merge, clean up worktree.**

**Estimate:** 15 min.

---

## Out of scope / follow-ups

- **Schema-migration tracking for `auth_health_status` table.** Initial schema is `CREATE TABLE IF NOT EXISTS`; if we add a column later (e.g., `last_error_class TEXT`), the next plan introduces a proper migration. Not now.
- **`/status` showing last-check timestamp** ("OAuth: ✓ rovik@majiq.agency (5 min ago)"). Stretch goal for a follow-up; the per-account ✓/✗ is the load-bearing info.
- **Initiative D** (web-based OAuth flow served by the bot) — v0.2.
