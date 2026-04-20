# Plan: Port Keep Warm from cos-agent to cosinabox

**Status:** Not started.
**Source:** `~/code/cos-agent/src/tools/attio_client.py` (598 lines; the relevant 3 phases land in PRs #137, #140, #143), `~/code/cos-agent/src/scheduler/briefing_pipeline.py` (keep_warm_result wiring).
**Target:** extend `cosinabox/tools/attio.py` + `cosinabox/jobs/morning_briefing.py`, + a new `keep_warm` tool family.
**Cutover tag:** **port** (from the cutover inventory).
**How to resume:** open this file, find the first `- [ ]` milestone, read its "Files touched" + "Tests" sections, start there. Self-contained; do not rely on chat context.

## Context / Why

Keep Warm is cos-agent's hand-curated list of people the maintainer cares about staying in touch with — ~30 contacts, each with a personal cadence (7 / 14 / 30 / 60 / 90 days). Every morning briefing surfaces the overdue ones so the user can nudge them before the relationship cools.

This is the newest user-visible feature from cos-agent (three PRs over weeks #137/#140/#143) and the cutover inventory ranks it as the biggest remaining gap. Without it, cosinabox's stakeholders.yaml-only model forces users to either hand-edit dates (no one does this) or enable the full Attio CRM integration just to get reminders.

The follow-up work porting commitments (#60) unblocked the pattern for this one: cos-agent uses Attio custom fields for per-person state (`keep_warm`, `keep_warm_cadence_days`, `keep_warm_note`, `last_interaction`) — we now know how to port Attio-backed features into the cosinabox shape.

## Non-goals

- **No Attio schema provisioning automation.** Attio users create the custom fields manually via Attio's UI; the docs describe which fields are required. cos-agent shipped a provisioning script that's maintainer-specific.
- **No replacement for existing `followup_reminder`.** That job uses `stakeholders.yaml` and now also gmail-last-sent (PR #57). Keep Warm is the Attio-backed superset. Both should coexist: users without Attio keep `followup_reminder`; users with Attio get richer overdue detection.
- **No relationship health score port** (cos-agent's `compute_relationship_health` is a separate surface that depends on interaction logs we haven't ported).
- **No Keep Warm CLI commands yet.** CLI integration is a follow-up after the core feature lands and is used in briefings. The agent-facing tools ship in this PR.
- **No changes to morning_briefing prompt beyond adding the KEEP WARM section.** Don't rewrite the prompt; append a targeted section.

## Prerequisites

- cosinabox's Attio integration (already shipped — `cosinabox.tools.attio`).
- Commitments port merged (#60) — not a code dep, but the pattern established there (tool family + briefing wiring) is what this plan mirrors.

## Milestones

### M1 — Attio client: read keep_warm custom fields

**Files touched:**
- `src/cosinabox/tools/attio.py` — extend the profile extractor to parse `keep_warm`, `keep_warm_cadence_days`, `keep_warm_note` from person records. Update the dataclass / return shape.

**Tests:** `tests/unit/test_attio_keep_warm.py` (new).

- [ ] Extend the internal `_extract_profile` helper to pull three new fields from Attio's `/objects/people/records` response:
  - `keep_warm: bool` (defaults False if missing)
  - `keep_warm_cadence_days: int | None`
  - `keep_warm_note: str | None`
- [ ] Add a default cadence constant `KEEP_WARM_DEFAULT_CADENCE_DAYS = 14` to `cosinabox.defaults`.
- [ ] Test fixtures: sample Attio response JSON with a keep_warm person, a non-keep_warm person, and a keep_warm person with null cadence.
- [ ] Tests:
  - `keep_warm=true` record → extracted correctly.
  - Missing fields → defaults (False / None / None).
  - Corrupt/empty fields → fallback to defaults, no exception.

**Estimate:** 90 min.

### M2 — Attio client: list_keep_warm + get_keep_warm_overdue

**Files touched:**
- `src/cosinabox/tools/attio.py` — new public methods on the tool.

**Tests:** extend `test_attio_keep_warm.py`.

- [ ] `list_keep_warm(*, limit=200) -> list[KeepWarmPerson]`:
  - Server-side filter: `POST /objects/people/records/query` with `{"limit": 200, "filter": {"keep_warm": true}}`.
  - Parse each record with the M1 extractor.
  - Compute `days_since_last_interaction` from the person's `last_interaction` timestamp.
  - Sort by `days_since` descending (oldest contact first, most overdue surfaced first). `None` days_since sorts last.
- [ ] `get_keep_warm_overdue() -> list[KeepWarmPerson]`:
  - Thin filter over `list_keep_warm`: return only people where `days_since > cadence_days`.
  - `days_since is None` → skip (no known last interaction).
- [ ] New `KeepWarmPerson` dataclass: `name`, `email`, `record_id`, `cadence_days`, `note`, `last_interaction`, `days_since`.
- [ ] Tests:
  - Mock Attio API responses; assert the filter query body is correct.
  - Empty response → `[]`.
  - Mix of overdue and not-overdue → `get_keep_warm_overdue` returns only the overdue ones, in days_since descending order.
  - `days_since=None` never appears in overdue.
  - Graceful handling of Attio API errors (log + return empty list, not exception).

**Estimate:** 2 hours.

### M3 — Attio client: set_keep_warm + unset_keep_warm

**Files touched:** `src/cosinabox/tools/attio.py`.

**Tests:** extend `test_attio_keep_warm.py`.

- [ ] `set_keep_warm(person: str, cadence_days: int, note: str | None = None)`:
  - Look up person by name (existing `get_profile`).
  - PATCH the person record with `keep_warm=true`, `keep_warm_cadence_days`, optional `keep_warm_note`.
  - Return status dict.
- [ ] `unset_keep_warm(person: str, note: str | None = None)`:
  - PATCH with `keep_warm=false`, clear `keep_warm_cadence_days`, optional new note (e.g., "deprioritized 2026-05-12").
- [ ] Validate cadence range: clamp to `[1, 365]`.
- [ ] Tests:
  - Happy path PATCH body assertion (JSON shape matches Attio's expected format).
  - Person not found → returns error dict, no PATCH call.
  - Clamping at bounds.

**Estimate:** 90 min.

### M4 — Morning briefing wiring

**Files touched:** `src/cosinabox/jobs/morning_briefing.py`.

**Tests:** extend `test_jobs_morning_briefing.py`.

- [ ] Add `attio: Any | None = None` param to `MorningBriefingJob`.
- [ ] In `_prefetch`, if `attio` is wired, call `get_keep_warm_overdue()` and format:
  ```
  KEEP WARM — OVERDUE:
    - Sarah Chen — 45d since last contact (cadence: 30d). Note: Lead Investor.
    - Tom Vasquez — 29d since last contact (cadence: 14d).
  ```
  Cap at 10 rows to prevent mega-briefings.
- [ ] Prompt addition (new bullet, minimal drift):
  ```
  5. KEEP WARM — overdue relationships from the curated list
     (see pre-fetched KEEP WARM — OVERDUE). Reference by name only;
     no record IDs.
  ```
- [ ] `app/jobs.py` plumbing: pass `tool_instances.get("attio")` into `MorningBriefingJob`.
- [ ] Tests:
  - With attio returning 2 overdue people → prompt contains both names + days_since.
  - With attio returning empty list → KEEP WARM section omitted entirely (don't say "no overdue contacts" — quiet when nothing's there).
  - With `attio=None` → no API call, no section, briefing falls back cleanly.

**Estimate:** 2 hours.

### M5 — Agent-facing tools

**Files touched:**
- `src/cosinabox/tools/attio.py` — register 3 tool definitions.
- `src/cosinabox/agent/policy.py` — allowlist `keep_warm_*`.

**Tests:** `tests/unit/test_tool_keep_warm.py` (new).

- [ ] `keep_warm_set(person, cadence_days, note?)` — wrap `set_keep_warm`.
- [ ] `keep_warm_unset(person, note?)` — wrap `unset_keep_warm`.
- [ ] `keep_warm_list()` — wrap `list_keep_warm`, return formatted string.
- [ ] Policy: `keep_warm_*` → ALLOW (priority 200). These only flip boolean Attio fields + cadence int; no PII exfiltration.
- [ ] Tests per tool:
  - Happy path, return string shape.
  - Person not found → error string (not exception).
  - `keep_warm_list` formatting matches briefing section shape.
- [ ] Register in `tools/registry.py` — gated on `"attio" in tool_instances`.

**Estimate:** 2 hours.

### M6 — User-repo docs

**Files touched:**
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — add a "Keep Warm" section under morning briefing.
- `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` — how to create the Attio custom fields (step-by-step screenshots optional, copy-paste field names required).

- [ ] Explain what Keep Warm is + required Attio custom fields:
  - `keep_warm` (checkbox / boolean)
  - `keep_warm_cadence_days` (number)
  - `keep_warm_note` (text)
- [ ] Example conversational commands: *"Mark Sarah as Keep Warm with 14-day cadence"*, *"Show me who's overdue on Keep Warm"*.
- [ ] Fallback note: without Attio, morning briefing still runs — the KEEP WARM section just doesn't appear.

**Estimate:** 1 hour.

### M7 — Commit, PR, merge

- [ ] Split commits by milestone for review.
- [ ] PR body links back to this plan + cos-agent source (#137, #140, #143).
- [ ] `gh pr create ... && gh pr merge --auto --squash`.

**Estimate:** 30 min.

### M8 — Cutover inventory + retro

**Files touched:**
- `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md` — flip the Keep Warm row.
- `docs/retros/2026-XX-XX-port-keep-warm.md` (new).

- [ ] Inventory PR in cos-agent.
- [ ] Retro covers estimate vs actual, Attio schema friction, whether manual-cadence-only UX needs follow-up.

**Estimate:** 30 min.

## Open questions for kickoff

1. **Attio schema provisioning.** cos-agent ships a one-shot provisioning script; cosinabox's philosophy has been "users do it via Attio UI." Confirm at M1 — a doc with field names is probably enough for OSS v1.
2. **Coexistence with `followup_reminder`.** Both will surface overdue people. Should the briefing prompt explicitly say "Keep Warm is from Attio; yaml staleness is from stakeholders.yaml — don't deduplicate"? Worth testing once both fire in production.
3. **Cadence UX.** cos-agent bakes in 7/14/30/60/90-day cadences but accepts any integer. Fine as-is.

## Total estimate

~10 hours. Bigger than the analytics gap but smaller than the commitments port. Realistic for one session.

## Out of scope / follow-ups

- **CLI commands** for `keep-warm set/unset/list` (conversational via agent is the primary path).
- **Relationship health score** (`compute_relationship_health` in cos-agent — separate surface).
- **Drive / calendar signals** for `last_interaction` (Attio tracks email + manual updates; cos-agent leaves calendar out).
- **Batch import from `stakeholders.yaml`** — a seed script that flips yaml-listed folks to Keep Warm on first run. Nice-to-have.
