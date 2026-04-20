# Editing config

Prefer **CLI commands over direct edits**. Prefer **config edits over prompt overrides**. Prefer **prompt overrides over custom Python**. In that order.

## Stakeholders

```bash
cosinabox add-stakeholder --name "Sarah Chen" --role "Lead investor (Sequoia)" --cadence weekly --notes "Wants monthly metric updates."
```

When adding a stakeholder, always ask the user for:
- Name (full name preferred)
- Role (one line)
- Cadence (`daily | weekly | biweekly | monthly | quarterly`)
- Notes (optional but encouraged — surface what makes this person useful)

Never leave fields blank. Never invent a cadence; ask.

## Jobs

```bash
cosinabox enable-job morning_briefing
cosinabox set-job-schedule morning_briefing --cron "0 8 * * *"
cosinabox disable-job followup_reminder
```

When enabling a new job, recommend simulate-mode for 2-3 days before relying on it:

```bash
cosinabox simulate <job_name>
```

## Personality

```bash
cosinabox set-persona --role founder
```

This loads the `founder` template. To customize beyond the template, run the persona interview (`docs/agent/persona-interview.md`). Never write a personality from a one-line user request — the result will be generic and the briefings will be too.

## Integrations

Each integration gives the CoS new capabilities. All are optional except Google (required for briefings). When a user asks "what can you do?" or "what integrations are available?", use this table.

| Integration | What it enables | Without it | Env var needed |
|-------------|----------------|------------|----------------|
| **google** | Email search, calendar events, briefings, pre-meeting prep, find free time, create events | Briefings have no email/calendar data. DM can't search mail or schedule. | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN_1` |
| **attio** | CRM contact search, relationship profiles, stakeholder tracking, **Keep Warm** reminders | Falls back to `stakeholders.yaml` — static, manually maintained, no search in DM, no Keep Warm | `ATTIO_API_KEY` |
| **fireflies** | Meeting transcript search, retrieve what was discussed | No meeting context — agent can't reference past conversations | `FIREFLIES_API_KEY` |
| **web_search** | Google search during DM conversations | Agent can only use information already in context | `SERPER_API_KEY` |
| **memory service** | Semantic recall, durable fact storage, extraction pipeline | Falls back to local SQLite with keyword search — works for <10k memories | `MEMORY_SERVICE_URL`, `MEMORY_API_KEY` |

### Adding an integration

1. Confirm the user has the API key (never guess or assume)
2. Add the key to `.env`
3. Set `enabled: true` in `integrations.yaml`
4. Run `cosinabox validate` to check config
5. Run `cosinabox describe` to confirm it appears in the summary

Never enable an integration without confirming the env var is set in `.env`.

### Attio — extra setup for Keep Warm

After enabling Attio, add three custom fields to the People object in Attio's UI (Settings → Objects → People → Attributes):

| Field slug | Type | Purpose |
|---|---|---|
| `keep_warm` | checkbox | True = include in the Keep Warm list. |
| `keep_warm_cadence_days` | number | Days between touches (e.g., 14). |
| `keep_warm_note` | text | Free-text reminder. |

Without these fields, the Attio integration still works but Keep Warm tools + the morning briefing's KEEP WARM section stay quiet.

## Setup & maintenance commands

| Command | When to use |
|---------|-------------|
| `cosinabox init <dir>` | First-time setup — scaffolds a new user repo |
| `cosinabox interview --start` | Walk through the 10-step persona interview |
| `cosinabox auth google` | Set up Google OAuth (Gmail + Calendar) |
| `cosinabox validate` | Check all config files for errors |
| `cosinabox describe` | Show a human-readable summary of current config |
| `cosinabox simulate <job>` | Dry-run a job locally (e.g., `simulate morning_briefing`) |
| `cosinabox doctor` | Run 10 health checks (secrets, schema, OAuth, etc.) |
| `cosinabox migrate` | Upgrade config files after a cosinabox version bump |

## After any edit

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary diff. If they're surprised, undo.
