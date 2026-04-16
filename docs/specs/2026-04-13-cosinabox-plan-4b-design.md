# Plan 4B: Intelligence — Extraction Pipeline, Post-Meeting Debrief, Rela

**Date:** 2026-04-13
**Status:** Design approved
**Depends on:** Plan 4A (memory client, structured logging)
**Estimated effort:** ~12h across 3 components (extract_drive deferred to Plan 5)

## Context

Plan 4A shipped the memory client (local SQLite + remote HTTP), structured logging, and analytics. Plan 4B adds the intelligence layer: extracting durable facts from data sources, post-meeting context, and relationship health tracking. All three are ported from cos-agent's battle-tested code, adapted for OSS.

**Design principles:**
1. Port from cos-agent, don't rewrite — the extraction pipeline, debrief logic, and Rela scoring are proven in production
2. OSS-friendly — stakeholder-based extraction (no hardcoded names), configurable via YAML
3. Graceful degradation — each component works independently; Fireflies missing doesn't break Gmail extraction

## 1. Extraction Pipeline

### What it does

Three daily scheduled jobs extract durable facts from external sources and store them in the memory client:

- **extract_fireflies** — pull meeting transcripts, extract decisions/participants/outcomes
- **extract_gmail** — pull emails from tracked stakeholders, extract commitments/context
- **extract_drive** — pull recently modified docs, extract key points

### Design

**Extraction target:** Stakeholders with cadence `daily` or `weekly` in stakeholders.yaml / Attio. Requires the `email` field on each stakeholder (added to the schema in this plan). Stakeholders without email are skipped with a debug log. Quarterly contacts aren't generating enough signal to warrant extraction.

**Idempotency:** Each source (transcript, email, doc) gets a unique key (`{source_type}:{source_id}`). Before extraction, check if already processed. After successful extraction, mark as processed. State stored in a `extraction_state` SQLite table:

```sql
CREATE TABLE IF NOT EXISTS extraction_state (
    key TEXT PRIMARY KEY,       -- "fireflies:{id}" or "gmail:{id}"
    processed_at TEXT NOT NULL
);
```

**Extraction prompt** (sent to Sonnet via the agent loop, not the memory service):

```
Extract durable facts from this content. Focus on:
- Decisions made and their rationale
- Commitments or action items (who, what, when)
- Stakeholder context (preferences, concerns, relationships)
- Key dates, amounts, or deadlines mentioned

Output as a JSON array of objects:
[{"text": "fact text", "metadata": {"source": "...", "date": "...", "stakeholder": "..."}}]

Only extract facts worth remembering weeks later. Skip pleasantries, logistics, and transient details.

Output ONLY the JSON array. No markdown fences, no preamble, no explanation.

CONTENT:
{content}
```

**Response parsing:** A `_parse_extraction_response(text)` helper strips markdown code fences, isolates the first `[` to last `]`, and parses with `json.loads()`. On malformed output, logs a warning and returns `[]` — never crashes.

Each extracted fact is stored via `memory_client.store(text=..., metadata=..., namespace="extraction")`.

**Three extractors:**

**extract_fireflies:**
- Schedule: daily 7:00 AM
- Queries Fireflies for transcripts from last 48h (wider window catches timezone edge cases)
- Skips stubs (transcripts with no sentences or duration < 60s)
- For each non-stub transcript: fetch summary (overview + action_items), run extraction prompt
- Idempotency key: `fireflies:{transcript_id}`
- Falls back gracefully if Fireflies not configured

**extract_gmail:**
- Schedule: daily 7:15 AM
- Builds query from active stakeholders: `from:{email1} OR from:{email2} OR ...`
- Only includes stakeholders with cadence `daily` or `weekly`
- Fetches emails from last 48h across all Gmail accounts
- For each email: format as `From: {sender}\nSubject: {subject}\n{snippet}`, run extraction prompt
- Idempotency key: `gmail:{message_id}`
- Falls back gracefully if Gmail not configured or no stakeholders match

**extract_drive:** Deferred to Plan 5 — requires a DriveTool that doesn't exist yet in the engine.

**Job output:** Each extractor returns a summary string (e.g., "Extracted 3 facts from 2 transcripts"). Wired to Telegram output via the standard `_wire_telegram_output` pattern — but only if facts were extracted (not on zero-result runs).

### OSS considerations

- No hardcoded stakeholder names — extraction targets come from stakeholders.yaml/Attio
- Drive extraction is optional (needs env var) — many users won't have shared Drive folders
- Fireflies is optional — extraction works with just Gmail
- All three extractors are independent — any combination works

## 2. Post-Meeting Debrief

### What it does

After a meeting ends, sends a Telegram message with key points, action items, and a prompt for the user to add context. If Fireflies has a transcript, includes its summary.

### Design

**Ported from:** `cos-agent/src/scheduler/briefing_pipeline.py` post_meeting_debrief function.

**Schedule:** Every 5 minutes (same cron as pre_meeting_prep, different check window).

**Detection logic:**
1. Query calendar for events that ended 15-30 minutes ago (normal mode) or up to 4 hours ago (catch-up on startup — handles restarts/downtime)
2. Deduplicate by iCalUID across accounts
3. Skip events already debriefed (tracked in `debrief_state` table)
4. Skip titles matching `skip_if_calendar_title_matches` from jobs.yaml (reuses pre_meeting_prep config)
5. Catch-up debriefs are flagged as "[Delayed debrief]" so the user knows it's not real-time

**Debrief state table:**
```sql
CREATE TABLE IF NOT EXISTS debrief_state (
    ical_uid TEXT PRIMARY KEY,
    debriefed_at TEXT NOT NULL
);
```

**Fireflies transcript matching** (ported from cos-agent, with improved disambiguation):
- Fetch transcripts from last 24h
- Match by: title substring, shared words (>2 chars), or attendee email overlap
- **Require at least 2 of 3 matching criteria** for generic titles (titles ≤2 words like "Sync", "1:1", "Standup")
- Add **time-proximity scoring**: transcript start time within ±30 min of calendar event start gets priority
- Skip stubs (no sentences or short duration)
- Sort candidates by: time proximity first, then quality (non-stub, duration)
- If ambiguous after scoring, include disclaimer: "Multiple transcripts matched — showing best guess"

**Output format:**
```
Meeting just ended: {title}
Attendees: {comma-separated names}

Key points:
{fireflies overview, truncated to 800 chars}

Action items:
{fireflies action_items, truncated to 500 chars}

Transcript captured by Fireflies.

Anything to add? Decisions, next steps, things that changed?
```

If no Fireflies transcript: "No transcript found yet (may still be processing)."

**CRM update:** After debrief, update `last_interaction` in Attio for external attendees (reuses CRM sync pattern from Plan 4A). Only if Attio is configured.

**Rela feed:** After debrief, feed meeting context to Rela sub-agent (if configured). Non-blocking — exceptions logged, don't block debrief.

### OSS considerations

- Works without Fireflies (just sends title + attendees, asks user to fill in)
- CRM update is optional (only if Attio enabled)
- Rela feed is optional (only if Rela configured)
- Reuses pre_meeting_prep's skip list — no new config needed

## 3. Rela — Relationship Manager

### What it does

A sub-agent that tracks relationship health for each stakeholder. Scores relationships 0-100 based on interaction patterns. Surfaces drift alerts when relationships cool. Queryable via DM ("how's my relationship with Alice?").

### Design

**Ported from:** `cos-agent/src/prompts/rela.py` + `src/subagent.py`.

**Sub-agent architecture:**

```python
class SubAgent:
    """Isolated agent with its own memory namespace and prompt."""
    name: str
    namespace: str          # memory namespace for isolation
    system_prompt: str      # specialized prompt
    model: str              # default: sonnet

    def ingest(self, content: str) -> None:
        """Fire-and-forget: runs AgentLoop in a background daemon thread.
        Returns immediately. Exceptions logged, never propagated."""

    def query(self, question: str) -> str:
        """Request-response: answer a question using namespace memories.
        Synchronous — blocks until response is ready."""
```

`ingest()` uses `threading.Thread(daemon=True).start()` to avoid blocking the caller (debrief, extraction). This matches the existing thread model (APScheduler + Telegram already use threads, SQLite is in WAL mode).

Sub-agents use the same `AgentLoop` but with:
- Custom system prompt (Rela's scoring instructions)
- Namespace-forced memory operations (all reads/writes go to `rela` namespace)
- Isolated session IDs (no conversation history bleed)

**Rela health scoring model** (simplified from cos-agent — v1 uses computable factors only):

| Factor | Weight | 100 score | 0 score | Data source |
|--------|--------|-----------|---------|-------------|
| Recency | 50% | Last contact <3 days | >30 days | `last_contact` from stakeholders.yaml/Attio |
| Meeting frequency | 50% | On cadence | 3x behind cadence | Calendar API query (meetings with stakeholder in last 30d vs expected cadence) |

Total = weighted sum. Stored per-stakeholder in `rela` namespace.

**Deferred to v2** (requires data model changes): email responsiveness (reply rate tracking), commitment follow-through (completion status), bidirectionality (inbound vs outbound counting). These can be added later as the extraction pipeline accumulates more structured data.

**How Rela gets data:** Rela's scoring prompt instructs it to query the calendar tool for meeting counts and read `last_contact` from stakeholder data. Post-meeting debrief feeds meeting context directly to Rela via `rela.ingest()`, which stores observations in the `rela` namespace. Daily extraction feeds relevant stakeholder facts to Rela the same way.

**What Rela tracks** (memory records in `rela` namespace):
- `relationship_health` — score per stakeholder, updated on each scan
- `drift_alert` — when health drops 20+ points or falls below 40
- `communication_pattern` — behavioral observations (e.g., "Alice always responds within 2h")
- `relationship_trend` — 90-day direction (warming/cooling/stable)

**Two scheduled operations:**
- `rela_daily_scan` (7:50 AM) — check VIP/Active stakeholders, update health scores
- `rela_weekly_audit` (Sunday 7:00 PM) — comprehensive audit, generate weekly digest

**DM query integration:** The CoS can answer "how's my relationship with X?" by querying Rela:
```python
rela = get_agent("rela")
answer = rela.query(f"Summarize relationship health for {name}")
```

This is exposed as a tool (`rela_query`) so Claude can call it during DM conversations.

**Constraint:** Rela is READ-ONLY for external systems. It reads from CRM, email, calendar, and commitments. It writes ONLY to its own memory namespace. No CRM updates, no emails, no calendar changes.

### OSS considerations

- Scoring model is configurable via the system prompt — users can adjust weights
- Works with just stakeholders.yaml (no Attio required for basic scoring)
- `rela_query` tool description explains what Rela knows and doesn't know
- Namespace isolation prevents Rela memories from leaking into main conversations

## Testing Strategy

| Component | Test file | Key test cases |
|-----------|-----------|----------------|
| Extraction | `test_extraction.py` | Idempotency (skip already-processed), stakeholder filtering (daily/weekly only), empty result handling, Fireflies stub detection, extraction prompt parsing |
| Post-meeting debrief | `test_post_meeting_debrief.py` | End window detection (15-30 min ago), already-debriefed skip, Fireflies matching (title, words, attendees), no-Fireflies fallback, CRM update on debrief |
| Rela | `test_rela.py` | Health score calculation, drift alert thresholds, namespace isolation, query response format, read-only constraint |
| Sub-agent | `test_subagent.py` | Namespace enforcement, session isolation, ingest vs query modes, timeout handling |

**Stress test checklist:**
- First run (no extraction state) — doesn't crash, extracts from 48h window
- Fireflies not configured — Gmail/Drive extractors still run
- No stakeholders match daily/weekly — Gmail extraction skips gracefully
- Meeting ended but no Fireflies transcript — debrief still sends with basic info
- Rela query for unknown stakeholder — returns "no data" not error
- Concurrent extractions — WAL mode handles it (from Plan 4A)

## Files

**New files:**
- `src/cosinabox/agent/subagent.py` — SubAgent class with ingest/query
- `src/cosinabox/agent/rela.py` — Rela prompts and registration
- `src/cosinabox/jobs/extract_fireflies.py`
- `src/cosinabox/jobs/extract_gmail.py`
- `src/cosinabox/jobs/post_meeting_debrief.py`
- `src/cosinabox/jobs/rela_scan.py` — daily + weekly Rela jobs
- `src/cosinabox/templates/user-repo/docs/agent/rela.md` — Rela docs for OSS users
- 4 test files

**Modified files:**
- `src/cosinabox/memory/sqlite.py` — add extraction_state + debrief_state tables
- `src/cosinabox/app.py` — register extraction jobs, debrief job, Rela sub-agent
- `src/cosinabox/tools/registry.py` — add rela_query tool definition + handler
- `src/cosinabox/templates/user-repo/jobs.yaml` — extraction + debrief + rela jobs (disabled by default)
- `src/cosinabox/templates/user-repo/stakeholders.yaml` — add optional `email` field with example
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — add new jobs to table
