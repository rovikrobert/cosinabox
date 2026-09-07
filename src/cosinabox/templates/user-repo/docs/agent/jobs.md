# Scheduled jobs

Your CoS runs background jobs on a schedule. Enable or disable them in `jobs.yaml`.

| Job | Default | Schedule | What it does |
|-----|---------|----------|-------------|
| auth_health | enabled | every 15 min | Probes Google refresh tokens; alerts on revocation. Run `cosinabox auth refresh` to fix. |
| job_watchdog | enabled | hourly | Alerts when a job stops firing at all. Every other check only catches a job that ran *badly*. |
| research_digest | disabled | Mon 8:30 AM | Weekly digest on the orgs and people you track. See setup below. |
| morning_briefing | enabled | 8:00 AM | Daily briefing: calendar, email, priorities |
| pre_meeting_prep | enabled | every 5 min | Sends context 30 min before meetings |
| evening_wrap | disabled | 6:00 PM | End-of-day summary |
| weekly_review | disabled | Fri 4:00 PM | Week recap |
| followup_reminder | disabled | 9:30 AM | Surfaces stale stakeholder contacts |
| inbound_email_check | disabled | every 5 min | Alerts on urgent inbound email |
| crm_email_sync | disabled | 5:45 PM | Updates CRM from today's sent emails |
| extract_fireflies | disabled | 7:00 AM | Extract facts from meeting transcripts |
| extract_gmail | disabled | 7:15 AM | Extract facts from stakeholder emails |
| post_meeting_debrief | disabled | every 5 min | Sends summary after meetings end |
| rela_daily_scan | disabled | 7:50 AM | Check relationship health |
| scheduling_poll_check | disabled | every 30 min | Poll participants for scheduling responses, nudge at 24h, expire at 48h (see `scheduling.md`) |

## Enabling a job

Tell Claude Code "enable the evening wrap" or use the CLI:

```bash
cosinabox enable-job evening_wrap
cosinabox set-job-schedule evening_wrap --cron "0 18 * * *"
```

## Gmail polling

Requires `urgent_senders` in `integrations.yaml` to know which emails to alert on. Without it, the job runs but never sends alerts.

## CRM sync

Requires both Google (Gmail) and Attio integrations enabled. Updates `last_interaction` timestamps only — no notes or status changes.

## Commitments (open work tracking)

`morning_briefing`, `evening_wrap`, and `weekly_review` all ground their open-work sections (PRIORITIES / CARRY-OVER / MISSES / NEXT WEEK) in the commitments table — **not in conversation memory**. Before surfacing an item as "still open," each job runs every commitment through `auto_resolve.verify_all_open_commitments`:

- Searches the last 7 days of sent mail for subject-line keyword matches.
- Emits one of three verdicts per commitment:
  - `VERIFIED_DONE` — 2+ distinct keyword matches in a subject.
  - `LIKELY_DONE` — a single keyword match.
  - `NO_EVIDENCE` — nothing found.

Only `NO_EVIDENCE` items can appear as carry-over / misses / priorities. This is the mechanism that prevents "zombie items" (resolved work reappearing in the briefing days later).

### Creating commitments

Tell Claude Code conversationally: *"remind me to follow up with Sarah on the Q3 deck by Friday"*. The agent calls `commitment_create` with the right fields. No need to edit YAML.

Also available: `commitment_list`, `commitment_update`, `commitment_close`, `commitment_dismiss`, `commitment_reopen`. All are read-only-by-default from a sandbox perspective (they only touch the local SQLite db — no outbound effects).

### Viewing state

```bash
cosinabox describe
```
shows counts by status (`open`, `done`, `cancelled`).

## Keep Warm (Attio-backed relationship reminders)

A hand-curated list of people you want to stay in touch with, each with a per-person cadence (e.g., every 14 days). The morning briefing surfaces them as overdue when days-since-last-contact exceeds their cadence.

Requires Attio CRM. Without Attio the section is silently omitted from the briefing; `stakeholders.yaml` + `followup_reminder` continue to work for the simpler cadence model.

### Required Attio custom fields (on the People object)

Create these once in the Attio UI (Settings → Objects → People → Attributes):

| Field | Type | Notes |
|---|---|---|
| `keep_warm` | checkbox | True = include in the Keep Warm list. |
| `keep_warm_cadence_days` | number | Days between touches (e.g., 14). |
| `keep_warm_note` | text | Free-text reminder (e.g., "Lead investor", "Q3 co-author"). |

**Note field rule:** relationship context only. No deadlines, no action items — those go in the commitments table. See `editing-config.md` for the full rule.

Attio also has a built-in `last_interaction` timestamp that we use to compute overdueness — no manual field needed.

### Using it conversationally

Tell Claude Code things like:

- *"Add Sarah Chen to Keep Warm, 14-day cadence, note: Lead investor."* → `keep_warm_set`
- *"Who's overdue on Keep Warm?"* → the briefing's KEEP WARM section, or `keep_warm_list`
- *"Drop Tom from Keep Warm, he moved on."* → `keep_warm_unset`

### Coexistence with followup_reminder

Both surface overdue people. Use Attio Keep Warm for the handful of relationships you care most about (per-person cadence + note); use `stakeholders.yaml` + `followup_reminder` for the broader stakeholder set with coarse weekly/monthly cadences. The briefing will show them as separate sections.

## research_digest — weekly digest on what you track

Disabled by default because it needs three things you must supply:

1. **`research.yaml`** in your repo root. Groups hold the orgs and people you
   want tracked; each entity contributes search queries. `priority` decides
   who survives the result cap — **lower numbers are kept first**, so give
   your few high-value groups a low number and a large noisy group a high one.
   A template ships with `cosinabox init`.
2. **`TAVILY_API_KEY`** in `.env`. Tavily specifically, because it exposes a
   news topic and a date window — a general web search over the same queries
   returns evergreen product pages, which then get discarded as not-recent.
3. **The `research` extra**: `pip install 'cosinabox[research]'` (Tavily
   client + RSS reader).

Miss any of the three and the job reports "not configured" and returns
without raising. It never partially runs.

### What it does

Collects candidates from your queries and any RSS feeds, drops off-topic feed
items, asks the cheapest model to filter out passing mentions, then makes one
streamed call to write the digest. Signals persist to `research_signals` —
**that table is the only place a signal survives after delivery**, so it is
primary data, not a cache. The store is backed up to `backups/` before each
run for that reason.

### What you lose by leaving it disabled

Nothing else depends on it. No other job reads `research.yaml`, and the
`research_signals` and `research_dedup` tables stay empty.

### When it complains

It pages on its own channel prefixed `research_digest:` — every search query
failing, no candidates collected, a synthesis that produced zero signals, and
output approaching the response ceiling. "The job ran" is deliberately not
treated as success: in the system this was ported from, a broken digest went
unnoticed for two weeks because nothing checked the output.
