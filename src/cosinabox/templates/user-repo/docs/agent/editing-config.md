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

Edit `integrations.yaml` directly. Set `enabled: true` for the integrations the user has set up. Never enable an integration without confirming the env var is set in `.env`.

## After any edit

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary diff. If they're surprised, undo.
