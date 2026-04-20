# Scheduled jobs

Your CoS runs background jobs on a schedule. Enable or disable them in `jobs.yaml`.

| Job | Default | Schedule | What it does |
|-----|---------|----------|-------------|
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

Attio also has a built-in `last_interaction` timestamp that we use to compute overdueness — no manual field needed.

### Using it conversationally

Tell Claude Code things like:

- *"Add Sarah Chen to Keep Warm, 14-day cadence, note: Lead investor."* → `keep_warm_set`
- *"Who's overdue on Keep Warm?"* → the briefing's KEEP WARM section, or `keep_warm_list`
- *"Drop Tom from Keep Warm, he moved on."* → `keep_warm_unset`

### Coexistence with followup_reminder

Both surface overdue people. Use Attio Keep Warm for the handful of relationships you care most about (per-person cadence + note); use `stakeholders.yaml` + `followup_reminder` for the broader stakeholder set with coarse weekly/monthly cadences. The briefing will show them as separate sections.
