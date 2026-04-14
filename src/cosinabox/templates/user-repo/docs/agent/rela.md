# Rela — Relationship Manager

Rela tracks relationship health for your stakeholders. It scores each relationship 0-100 and surfaces drift alerts when contacts cool.

## How it works

Rela runs as a background sub-agent with its own memory namespace. It reads from your calendar and stakeholder data but never modifies external systems (read-only).

## Scoring (v1)

| Factor | Weight | Best | Worst |
|--------|--------|------|-------|
| Recency (days since last contact) | 50% | <3 days = 100 | >30 days = 0 |
| Meeting frequency vs cadence | 50% | On cadence = 100 | 3x behind = 0 |

## Asking about relationships

In a DM conversation, ask your CoS:
- "How's my relationship with Alice?"
- "Who am I losing touch with?"
- "Show me relationship health for my VIPs"

## Enabling Rela

Tell Claude Code "enable Rela" or edit jobs.yaml to enable `rela_daily_scan` and `post_meeting_debrief`.
