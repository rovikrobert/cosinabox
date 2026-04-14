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
