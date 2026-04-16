# Plan 4A: Foundation — Memory, Logging, Analytics, Gmail Polling, CRM Sync

**Date:** 2026-04-12  
**Status:** Design approved  
**Depends on:** Plan 3 (complete)  
**Blocks:** Plan 4B (extraction, debrief, Rela), Plan 4C (scheduling, webhooks)  
**Estimated effort:** ~14h across 5 components  

## Context

Plan 3 shipped tools in DM, bot commands, conversation summarization, and the policy engine. Plan 4A adds the foundation layer that Plans 4B and 4C depend on: persistent memory, structured logging, analytics, and two new scheduled jobs.

**Design principles (from engine CLAUDE.md):**
1. Local-first — everything works with `cosinabox init` + zero external services
2. OSS-friendly — no hardcoded names, all config via YAML, tradeoffs documented
3. Stress-test-aware — deduplication, error classification, graceful skip on disabled integrations
4. Privacy-conscious — logs store metadata (tool name, duration, error type), never input/output content

## 1. Memory Service Client

### Problem

The extraction pipeline (Plan 4B) and Rela (Plan 4B) need a way to store and retrieve durable facts (decisions, stakeholder context, meeting outcomes). The cos-agent uses an external Railway-hosted memory service. OSS users shouldn't need to deploy a second service.

### Design

**Interface:** A `MemoryClient` protocol with two backends.

```python
class MemoryClient(Protocol):
    def store(self, *, text: str, metadata: dict, namespace: str) -> str: ...
    def recall(self, *, query: str, namespace: str, limit: int = 5) -> list[dict]: ...
    def search(self, *, query: str, namespace: str) -> list[dict]: ...
    def delete(self, *, memory_id: str) -> bool: ...
```

**LocalMemoryClient** (default, zero config):
- SQLite table in `.cosinabox/memory.db`:
  ```sql
  CREATE TABLE IF NOT EXISTS memories (
      id TEXT PRIMARY KEY,        -- uuid
      text TEXT NOT NULL,
      metadata_json TEXT NOT NULL, -- JSON blob
      namespace TEXT NOT NULL,
      created_at TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_memories_ns ON memories (namespace);
  ```
- `recall()` and `search()` use `LIKE %keyword%` on `text` + `metadata_json` with LIKE wildcards escaped (`%` → `\%`, `_` → `\_`, `ESCAPE '\'`). Not semantic, but functional for <10k memories. Performance note: full table scan at O(n), documented as degrading above 10k rows. FTS5 is a future upgrade path (zero-dependency, ships with SQLite).
- Parameterized queries (`?` placeholders) are mandatory for all SQL — never string-format user input.
- Returns results sorted by recency (newest first).
- `store()` generates a UUID, inserts row, returns the ID.

**RemoteMemoryClient** (opt-in via env var):
- HTTP client to external memory service.
- Endpoints: `POST /memories`, `POST /recall`, `POST /search`, `DELETE /memories/{id}`.
- Auth: Bearer token via `MEMORY_API_KEY`.
- Namespace filtering via query param.
- Timeout: 5s per request. On failure: log warning, return empty results (graceful degradation).

**Resolution in App.run():**
- If `MEMORY_SERVICE_URL` is set in `.env` → `RemoteMemoryClient`
- Otherwise → `LocalMemoryClient` using the existing `.cosinabox/memory.db`

**Template updates:**
- `.env.example`: add `# MEMORY_SERVICE_URL=` and `# MEMORY_API_KEY=` (commented out)
- `integrations.yaml`: no change needed (memory is infra, not an integration toggle)
- `docs/agent/editing-config.md`: add memory service row to setup commands table

### Tradeoff documentation (for OSS users)

The `describe` command output will include:
```
Memory: local (keyword search, .cosinabox/memory.db)
```
or:
```
Memory: remote (semantic search, https://your-service.railway.app)
```

The `docs/agent/editing-config.md` integration table gains a row:
| **memory service** | Semantic recall, durable fact storage, extraction pipeline | Falls back to local SQLite with keyword search — works for <10k memories | `MEMORY_SERVICE_URL`, `MEMORY_API_KEY` |

## 2. Structured Logging

### Problem

Cost tracking is in-memory only (lost on restart). Tool errors are logged to stdout but not queryable. Job execution history doesn't exist. Analytics and doctor checks need structured data.

### Design

**SQLite threading safety:** All DB access must use `PRAGMA journal_mode=WAL` (write-ahead log) and `check_same_thread=False` on the connection. APScheduler runs jobs in threads; the Telegram handler runs in an async event loop. Both share the same DB file. WAL allows concurrent reads with serialized writes. Without this, `database is locked` errors will occur under normal operation.

**Three new tables** in `.cosinabox/memory.db`:

```sql
CREATE TABLE IF NOT EXISTS tool_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_type TEXT NOT NULL DEFAULT 'none',  -- none|auth|rate_limit|timeout|api_error|validation
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_logs_created ON tool_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_tool_logs_tool ON tool_logs (tool_name);

CREATE TABLE IF NOT EXISTS daily_costs (
    date TEXT PRIMARY KEY,        -- YYYY-MM-DD
    total_cost REAL NOT NULL DEFAULT 0,
    opus_calls INTEGER NOT NULL DEFAULT 0,
    sonnet_calls INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,          -- success|error|no_output
    output_length INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_runs_created ON job_runs (created_at);
```

**Privacy:** `tool_logs` stores tool name + duration + error type. Never stores input parameters or output content. This is a deliberate choice — OSS users should not have their emails, calendar events, or CRM data sitting in a log table.

**Integration points:**

- **AgentLoop** (after tool dispatch): writes `tool_logs` row with name, duration, error classification
- **CostTracker.record()**: uses atomic SQL increment (`UPDATE daily_costs SET total_cost = total_cost + ? WHERE date = ?`) instead of load-modify-write. This prevents race conditions between the DM handler and scheduled jobs calling `record()` concurrently. The in-memory `_daily_spend` dict is protected by a `threading.Lock` for the budget gate check. On init, loads today's row to restore the running total.
- **SchedulerRunner** (after job completes): writes `job_runs` row

**Error classification function:**
```python
def classify_error(exc: Exception) -> str:
    """Classify exception into a loggable bucket.
    
    Checks exception type first (reliable for httpx/anthropic),
    then status_code attribute (Google API, httpx), then falls
    back to string matching.
    """
    # 1. Check exception class name (catches httpx.ConnectTimeout, etc.)
    exc_type = type(exc).__name__.lower()
    if "timeout" in exc_type:
        return "timeout"
    if "ratelimit" in exc_type:
        return "rate_limit"
    
    # 2. Check status_code attribute (httpx, anthropic, googleapiclient)
    status = getattr(exc, "status_code", None)
    if status is None:
        # googleapiclient uses resp.status
        resp = getattr(exc, "resp", None)
        if resp:
            status = getattr(resp, "status", None)
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "auth"
    if status and status >= 500:
        return "api_error"
    
    # 3. Fall back to string matching
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "429" in msg or "rate" in msg:
        return "rate_limit"
    if "401" in msg or "403" in msg or "auth" in msg:
        return "auth"
    if "invalid" in msg or "missing" in msg or "required" in msg:
        return "validation"
    return "api_error"
```

## 3. Analytics

### Problem

Users need visibility into their CoS's operational health: how much it costs, which tools fail, whether jobs are running.

### Design

**Analytics module** (`agent/analytics.py`): pure query functions over the logging tables.

```python
def get_cost_summary(db) -> dict:
    """Today's spend, 7-day average, trend."""

def get_tool_stats(db, days: int = 7) -> dict:
    """Top 5 tools by call count, error rate per tool."""

def get_job_health(db, days: int = 7) -> dict:
    """Runs today, failures last 7 days, longest job."""

def get_error_summary(db, hours: int = 24) -> dict:
    """Top 3 error types in last N hours."""
```

**Exposed via:**
- `/analytics` bot command — calls all four functions, formats as text
- `cosinabox doctor` — three new checks:
  - `cost_persistence`: daily_costs has a row for today (warning if empty after first hour)
  - `tool_error_rate`: overall error rate < 20% in last 7 days
  - `job_failure_rate`: no single job failing >3x in last 7 days
- `cosinabox describe --json` — includes `analytics` key with snapshot

**No autonomy scoring.** The policy engine's static rules handle approval gating. Autonomy graduation (auto-execute based on approval history) is deferred — the logging tables support it later without schema changes.

**Discoverability:** `/help` command updated to include `/analytics`. The system prompt (`render_system_prompt`) gains a `## Capabilities` section listing enabled bot commands, active jobs, and enabled integrations — so users can ask "what can you do?" via DM and get an accurate answer. A new `docs/agent/jobs.md` template describes all available scheduled jobs with enable/disable instructions.

## 4. Gmail Polling

### Problem

Users want to know about important inbound emails without setting up Google webhooks (which require a public HTTPS endpoint). A simple cron job covers 90% of the use case.

### Design

**New scheduled job:** `inbound_email_check`

**Schedule:** Every 5 minutes (configurable via `poll_interval_minutes` in integrations.yaml)

**Flow:**
1. Load last-check timestamp from SQLite (`gmail_poll_state` table). On first run (no row exists), default to `now - poll_interval_minutes` — only fetch the last 5 minutes, never the full inbox.
2. Query Gmail: `after:{last_check_epoch}` across all accounts
3. Deduplicate by message ID: check each message ID against `processed_message_ids` table (persistent across restarts) AND in-memory set (cross-account dedup within this cycle)
4. For each new message, check if sender matches urgency list
5. If urgent → send Telegram alert: `[URGENT EMAIL] From: {sender} | Subject: {subject}\n{snippet}`
6. If non-urgent → log silently (data available in morning briefing)
7. Update `last_check_ts` per-message after each message is processed (not at end of batch — narrows the restart-duplicate window to a single message)
8. Insert processed message IDs into `processed_message_ids`

**State tables:**
```sql
CREATE TABLE IF NOT EXISTS gmail_poll_state (
    account_index INTEGER PRIMARY KEY,
    last_check_ts TEXT NOT NULL  -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS processed_message_ids (
    message_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
-- Prune entries older than 7 days on each poll cycle to prevent unbounded growth.
```

**Urgency config in `integrations.yaml`:**
```yaml
integrations:
  google:
    enabled: true
    urgent_senders:
      - "@yourcompany.com"      # domain match (right-of-@)
      - "investor@vc.com"       # exact email match
    poll_interval_minutes: 5
```

**Matching logic:** For each sender email, check:
1. Exact match against `urgent_senders` list
2. Domain match: extract `@domain.com` from sender, check if `@domain.com` is in the list

**Fallbacks:**
- Google not configured → job skips silently
- No `urgent_senders` configured → job runs but never alerts (all emails are "non-urgent")
- Gmail API error → log warning, retry next cycle

**Template updates:**
- `jobs.yaml`: `inbound_email_check: {enabled: false, schedule: "*/5 * * * *"}`
- `integrations.yaml`: `urgent_senders` field with comment explaining domain vs exact match
- `docs/agent/editing-config.md`: mention in jobs section

## 5. CRM Sync

### Problem

After sending emails, the CRM's `last_interaction` date goes stale unless manually updated. Automating this keeps stakeholder tracking accurate.

### Design

**New scheduled job:** `crm_email_sync`

**Schedule:** Daily at 5:45 PM (configurable)

**Flow:**
1. Fetch today's sent emails: `gmail.search("in:sent after:{today}")` across all accounts
2. For each sent email, extract recipient addresses (To + CC)
3. For each recipient, check if they exist in Attio (via `attio.search_people(email)`)
4. If found → update `last_interaction` field via Attio API
5. Log: "CRM sync: updated 4 interactions"

**What it updates:** Only `last_interaction` timestamp. No notes, no relationship status changes. Those are explicit DM tool calls.

**Attio free plan safe:** Uses `search_people` (query endpoint) + update via existing `AttioClient.update_person()`. No custom fields required. Compatible with free tier per memory `project_attio_free_plan.md`.

**Fallbacks:**
- Attio not configured → job skips silently
- Gmail not configured → job skips silently
- Attio API error on individual update → log warning, continue to next recipient. On 429 (rate limit), back off 2s before continuing. Three consecutive 429s aborts the batch with a clear log message. Log count reflects successful updates only (e.g., "CRM sync: 17/20 interactions updated, 3 failed").

**Template updates:**
- `jobs.yaml`: `crm_email_sync: {enabled: false, schedule: "45 17 * * *"}`

## Testing Strategy

Each component gets its own test file following the engine's existing patterns:

| Component | Test file | Key test cases |
|-----------|-----------|----------------|
| Memory client | `test_memory_client.py` | Local store/recall/search/delete, remote mock, resolution logic, keyword matching |
| Structured logging | `test_structured_logging.py` | tool_logs write/query, daily_costs persistence across restart, error classification |
| Analytics | `test_analytics.py` | Cost summary, tool stats, job health, empty tables (day 1), doctor checks |
| Gmail polling | `test_gmail_polling.py` | Urgency matching (domain, exact, miss), deduplication, state persistence, no-config skip |
| CRM sync | `test_crm_sync.py` | Match found → update, no match → skip, batch error resilience, no-attio skip |

**Stress test checklist (run after each component):**
- Empty state (first run, no data) — does it crash or degrade gracefully?
- Missing integrations — does the job skip without error?
- API failures — are they caught and classified, not propagated?
- OSS names — no hardcoded names in descriptions, logs, or error messages
- Discoverability — is the feature documented in agent-facing docs?
- Tradeoff clarity — does the user know what they gain/lose by enabling/disabling?

## Files Changed (Estimated)

**New files:**
- `src/cosinabox/memory/client.py` — MemoryClient protocol + LocalMemoryClient + RemoteMemoryClient
- `src/cosinabox/agent/analytics.py` — query functions over logging tables
- `src/cosinabox/agent/logging.py` — ToolLogger, error classification
- `src/cosinabox/jobs/inbound_email_check.py` — Gmail polling job
- `src/cosinabox/jobs/crm_email_sync.py` — CRM sync job
- `src/cosinabox/templates/user-repo/docs/agent/memory.md` — memory service docs
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — scheduled jobs reference
- 5 test files

**Modified files:**
- `src/cosinabox/memory/sqlite.py` — add logging + gmail_poll_state tables to schema
- `src/cosinabox/agent/loop.py` — write tool_logs after dispatch
- `src/cosinabox/agent/cost.py` — CostTracker persistence via daily_costs table
- `src/cosinabox/scheduler/runner.py` — write job_runs after completion
- `src/cosinabox/app.py` — instantiate MemoryClient, register new jobs, wire analytics
- `src/cosinabox/bot/commands.py` — add /analytics command
- `src/cosinabox/cli/describe.py` — show memory backend + analytics in describe output
- `src/cosinabox/doctor/checks.py` — add cost_persistence, tool_error_rate, job_failure_rate checks
- `src/cosinabox/templates/user-repo/integrations.yaml` — urgent_senders field
- `src/cosinabox/templates/user-repo/jobs.yaml` — two new jobs (disabled by default)
- `src/cosinabox/templates/user-repo/.env.example` — memory service vars
- `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` — memory row in integration table
- `src/cosinabox/prompts/core.py` — add Capabilities section to system prompt
