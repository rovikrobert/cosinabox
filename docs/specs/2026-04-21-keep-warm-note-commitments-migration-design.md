# Keep Warm note ↔ commitments migration — design

**Date:** 2026-04-21
**Status:** draft
**Related code:** `src/cosinabox/commitments/`, `src/cosinabox/tools/attio.py`, `src/cosinabox/jobs/morning_briefing.py`

## Problem

The morning briefing surfaces Keep Warm rows with their `keep_warm_note` field concatenated verbatim into the prompt. When the note contains commitment-like free text — e.g. `"Send proposal by Friday. SOW with Daniel is a key priority"` — the model renders that text as an obligation inside the `KEEP WARM — OVERDUE` section, even though the authoritative commitments table is empty. The same briefing correctly reports "no open commitments tracked" at the end, producing an apparent contradiction: the briefing names a specific commitment, then denies any exist.

Data trail:

- `src/cosinabox/jobs/morning_briefing.py:122-127` appends `. Note: {p.note}` to each KEEP WARM row in the prefetched prompt.
- `p.note` is the Attio `keep_warm_note` attribute (`src/cosinabox/tools/attio.py:130-131`), populated by the agent-facing `set_keep_warm` tool (`src/cosinabox/tools/attio.py:259-297`).
- The `commitments` SQLite table is authoritative, but nothing prevents commitment-shaped content from accumulating in the Attio note as a parallel free-text channel.

The prior commitments-table port made that table the single source of truth for commitments. Keep Warm notes were left as free-text and now leak commitment-shaped content back into briefings, undermining that invariant.

## Goals

1. Define and enforce a semantic boundary for what belongs in `keep_warm_note`.
2. Surface existing leaks so the user can migrate them into the commitments table.
3. Prevent re-accumulation of the leak over time, across both agent-mediated writes and Attio web-UI edits.
4. Preserve historical note content so cleanup and evolution don't destroy relationship context.

## Non-goals

- Restructuring the `commitments` table or adding new commitment fields.
- Changing the briefing prompt's existing commitment-verification logic.
- Versioning non-note Keep Warm fields (cadence, `keep_warm` boolean).
- Blocking users from putting commitment-like text into a note. The engine warns; it does not veto.
- Backfilling history from Attio's own activity log — we only have visibility from the schema-migration date forward.
- A CLI wrapper for the migration. The agent tool suffices for the conversational flow; a CLI is future work if batch use ever materializes.

## Semantic boundary

Load-bearing sentence, appearing verbatim in:

1. `set_keep_warm`'s tool description in `src/cosinabox/tools/registry.py` (agent-facing — this is the copy that matters most).
2. `KeepWarmPerson.note` Python docstring (`src/cosinabox/tools/attio.py`).
3. `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` and anywhere else the user-repo template documents Keep Warm.

> **Note field = relationship context: who they are, how you know them, what they care about, what makes this relationship current.** No future-tense actions, no deadlines, no items you owe them. If a line tells you what to *do* or *when*, it's a commitment — track it in the commitments table.

Canonical cases:

| Line | In note? | Why |
|---|---|---|
| "triathlete, son Oliver just started college" | ✓ | what they care about |
| "introduced by Sarah 2023; mentor 5y" | ✓ | how you know them |
| "SVP at Acme, owns Series B decision" | ✓ | who they are / what's current |
| "SOW with Daniel is a key priority" | ✓ | status — no owed action, no date |
| "Send proposal by Friday" | ✗ | what + when → commitment |
| "Follow up after Q2 earnings" | ✗ | what + when → commitment |
| "Waiting on SOW from Daniel" | split | note: "SOW is a key priority"; commitment: stakeholder=Daniel, title="SOW arriving", no owner-side deadline |

## Design

### 1. Write-time guardrail in `set_keep_warm`

`src/cosinabox/tools/attio.py`, method `set_keep_warm`: before patching Attio, run a regex against the incoming `note` argument.

Regex matches (conservative-but-broad — bias toward false positives under soft-warn semantics):

- Deadline phrases: `by <weekday|date|EOD|EOW|EOM>`, `before <date>`, `this|next week`, `this|next month`, `in N (days|weeks|months)`.
- Action-verb + date combos: `(send|reply|respond|share|submit|deliver|follow.?up|email|call|ping|sign) X (by|before|this|next) Y`.
- Explicit calendar words: `Friday`, `Monday`, …, `Jan`, `Tuesday 5pm`, `Q[1-4]`.

Does **not** match pure status language with no deadline: `"key priority"`, `"important"`, `"owns decision"`.

Behavior:

- No match → write as today; return `{"status": "ok", ...}` unchanged.
- Match → write still succeeds (engine does not veto explicit user updates); response includes `{"status": "ok", "warning": "note_looks_like_commitment", "matched": "<offending substring>"}`.

**Prompt addition.** One generalized line in `src/cosinabox/prompts/core.py`:

> If a tool response contains a `warning` field, surface it to the user verbatim and ask how they want to proceed before moving on.

This is not feature-specific — any tool can emit a `warning` going forward.

### 2. Migration tool

New module `src/cosinabox/commitments/migrate_from_keep_warm.py`, lazy-imported so users without Attio don't pay the import cost.

New agent tool `review_keep_warm_notes` in the tool registry. **Read-only.** Behavior:

1. Fetch all `keep_warm=True` people via `attio.list_keep_warm`.
2. Run the shared regex (section 1) against each person's note.
3. Return a structured list of flagged rows only:
   ```python
   [
       {
           "person": "Daniel Klaus",
           "record_id": "...",
           "note": "Send proposal by Friday. SOW is a key priority",
           "regex_matches": ["Send proposal by Friday"],
           "days_since": 14,
           "cadence_days": 14,
       },
       ...
   ]
   ```

No internal Claude call. Extraction (title, deadline, stakeholder, priority, cleaned note) happens in the agent loop, where the user can see and correct the reasoning. The agent walks the list item-by-item over Telegram; user approves / edits / skips each.

On per-item approval the agent uses **existing** tools:

- `commitments.add(...)` for the extracted commitment(s).
- `set_keep_warm(person=..., cadence_days=<unchanged>, note=<cleaned>, reason="migration")` for the cleaned note. The history snapshot (section 4) happens automatically in that call.

No new write-tool is introduced, keeping surface area small.

### 3. Briefing-time leak detector

`src/cosinabox/jobs/morning_briefing.py` `_prefetch`, alongside the existing KEEP WARM block:

- After the existing overdue-rows query, count how many `keep_warm=True` rows have notes that match the regex.
- If count > 0, append a single line to the prefetched data:
  ```
  KEEP WARM — LEAKED: <N> notes look commitment-shaped. Ask me to review.
  ```

Rationale: the write-time guardrail (section 1) only fires when the agent calls `set_keep_warm`. Notes edited directly in Attio's web UI bypass it; the briefing detector closes that gap without an LLM cost (pure regex; only emits a line when non-zero).

### 4. Note history (snapshot on write)

New SQLite table in the user's cosinabox DB:

```sql
CREATE TABLE keep_warm_note_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_record_id  TEXT    NOT NULL,
    person_name       TEXT,
    note              TEXT    NOT NULL,
    archived_at       TEXT    NOT NULL,  -- ISO-8601 UTC
    reason            TEXT              -- 'user_update' | 'migration' | NULL
);
CREATE INDEX idx_kwh_person_time
    ON keep_warm_note_history (person_record_id, archived_at DESC);
```

`set_keep_warm` picks up a new optional parameter: `reason: str | None = None`. Contract:

- Read current note from Attio.
- If current note is non-empty **and differs from** incoming note, insert a row into `keep_warm_note_history` with `reason = reason or "user_update"`.
- Proceed with the Attio patch.

Migration tool's apply path goes through the same `set_keep_warm`, passing `reason="migration"`. Explicitly clearing a note (setting it to `""`) still snapshots the prior non-empty value. The `reason` parameter is not forwarded to Attio — it's a history-only annotation.

New agent tool `get_keep_warm_history(person)`: returns archived rows for that person, newest-first. Lets the user ask "what did I used to have written about Daniel?" over chat.

**Retention.** Forever in v1. Rows are small; pruning is a trivial follow-up if volume ever becomes a concern.

**Scope.** `note` field only. History for cadence or the `keep_warm` boolean is a separate feature if ever wanted.

**Schema version.** Additive change → bump `schema_version` for the user DB, ship a `cosinabox migrate` migration in the same PR (CLAUDE.md rule 5).

## Files touched

**New:**

- `src/cosinabox/commitments/migrate_from_keep_warm.py` — shared regex, flagged-row fetcher, tool glue.
- Migration script under the existing `cosinabox migrate` infrastructure — exact path TBD in the plan step per the repo's migration convention.
- `tests/unit/test_migrate_from_keep_warm.py`
- `tests/unit/test_keep_warm_note_history.py`

**Modified:**

- `src/cosinabox/tools/attio.py` — regex guardrail + history-snapshot hook in `set_keep_warm`; updated `KeepWarmPerson.note` docstring.
- `src/cosinabox/memory/sqlite.py` (or a new adjacent module) — CRUD for `keep_warm_note_history`.
- `src/cosinabox/tools/registry.py` — update `set_keep_warm` description (semantic-boundary first line); register `review_keep_warm_notes`, `get_keep_warm_history`.
- `src/cosinabox/jobs/morning_briefing.py` — briefing-time leak detector.
- `src/cosinabox/prompts/core.py` — generalized "surface warnings" rule.
- `src/cosinabox/agent/policy.py` — register new tools in the policy allowlist if applicable.
- `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` — semantic-boundary line.
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — note-vs-commitment distinction in the Keep Warm section.

## Testing

Unit:

- Regex positive/negative coverage — at least 20 cases across deadline, action+date, and pure-status categories.
- `set_keep_warm` happy path (note changes, no regex match) unchanged.
- `set_keep_warm` with a flagged note returns `warning`; the Attio write still happens.
- `set_keep_warm` snapshots the old note to `keep_warm_note_history` on any change; no snapshot when old==new; snapshot when incoming is empty and old was non-empty.
- `get_keep_warm_history` returns newest-first.
- `review_keep_warm_notes` returns only flagged rows; no Claude call.
- Briefing-time leak detector: 0 flagged → no section; N>0 → exactly one `KEEP WARM — LEAKED: N …` line.
- Schema migration: forward-apply on a pre-schema DB creates the table and index; idempotent re-apply is a no-op.

Integration:

- End-to-end: seed a keep-warm person with a commitment-shaped note → `review_keep_warm_notes` flags it → agent approves (simulated) → `commitments` row inserted, Attio note cleaned, history row with `reason="migration"`.

## Stress-test risks (accepted)

- **Non-atomic apply in the migration step.** The agent calls `commitments.add` then `set_keep_warm(note=cleaned)`. If the second call fails (Attio 429, outage), the commitment is created but the note still reads as pending. The next migration run sees the commitment already exists and flags only still-pending content — self-healing. No transactional wrapper.
- **Regex false positives.** Under soft-warn semantics, cost is one dismissed warning per false hit. Acceptable.
- **Attio web-UI edits bypass the write-time guardrail.** The briefing-time detector (section 3) closes the gap on the next morning briefing. Latency of up to 24h is acceptable.
- **OSS relevance is narrow.** Feature only fires for users with Attio + populated keep-warm notes + dense free-text. Lazy-import the migration module so it imposes zero cost on installs without Attio.

## Open questions (resolved in plan step)

1. **Exact migration filename / directory convention.** Inspect `src/cosinabox/memory/` and any existing `cosinabox migrate` infrastructure during the plan step; follow the established pattern.
2. **`get_keep_warm_history` in the briefing?** Not for v1. Could be a follow-up: "Daniel's note changed 3 days ago — want to see what it used to say?"
3. **Should the migration module be extras-gated?** Probably not — regex + SQLite only. Attio is already an extra (`cosinabox[attio]`); the migration tool's runtime cost is bound by whether `attio` is available, not by a separate import-time cost.

## Next step

Once this spec is reviewed and signed off, invoke `superpowers:writing-plans` to produce the implementation plan.
