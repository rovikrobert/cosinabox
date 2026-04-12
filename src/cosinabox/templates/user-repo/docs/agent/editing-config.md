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
| **attio** | CRM contact search, relationship profiles, stakeholder tracking synced with Attio | Falls back to `stakeholders.yaml` — static, manually maintained, no search in DM | `ATTIO_API_KEY` |
| **fireflies** | Meeting transcript search, retrieve what was discussed | No meeting context — agent can't reference past conversations | `FIREFLIES_API_KEY` |
| **web_search** | Google search during DM conversations | Agent can only use information already in context | `SERPER_API_KEY` |

### Adding an integration

1. Confirm the user has the API key (never guess or assume)
2. Add the key to `.env`
3. Set `enabled: true` in `integrations.yaml`
4. Run `cosinabox validate` to check config
5. Run `cosinabox describe` to confirm it appears in the summary

Never enable an integration without confirming the env var is set in `.env`.

## After any edit

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary diff. If they're surprised, undo.
