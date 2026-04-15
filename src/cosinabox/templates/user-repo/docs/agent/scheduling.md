# Scheduling

Multi-person meeting coordination. Tell your CoS "find time for me and Alice and Bob next week" and it will:

1. Find optimal slots across everyone's timezones (hard-blocks 1-6am local for every participant)
2. Show you the top candidates and wait for your approval
3. Send polls via Telegram DM (when participant has a Telegram ID) or draft Gmail replies (never auto-sent)
4. Poll every 30 min for responses, nudge at 24h, expire at 48h
5. Surface consensus once everyone agrees, or escalate back to you if it stalls

## Current limitations

**Phase B deferred (Plan 5):** When you confirm a slot, the scheduling state transitions to `BOOKED` but the calendar event is NOT yet created automatically. Your CoS will tell you the agreed time — create the event manually in Google Calendar until a later release wires this up.

Other known gaps:
- Only the owner's calendar is consulted for conflicts. Participant availability is self-reported via their poll response.
- Gmail replies are parsed via Sonnet; highly ambiguous text falls back to asking you to interpret.

## Enabling scheduling

1. Uncomment `scheduling_poll_check` in `jobs.yaml` (the polling job). The 3 scheduling tools (`schedule_group_meeting`, `scheduling_status`, `scheduling_respond`) are auto-registered whenever that job is enabled OR a `scheduling:` section exists in `integrations.yaml`.
2. Optionally tune `scheduling.*` in `integrations.yaml` — every field has a safe default.
3. Ask your CoS, for example: _"schedule a 45-minute sync next week with Alice (alice@example.com, Europe/Berlin) and Bob (bob@example.com, Asia/Tokyo)."_

## Configuration reference

All keys live under `scheduling:` in `integrations.yaml`:

| Key | Purpose |
|-----|---------|
| `peak_hours` | `[start, end]` hours (local) that score highest — default `[9, 12]` |
| `avoid_hours` | `[start, end]` de-preferred hours (e.g. lunch) — default `[12, 13]` |
| `workday_hours` | Outside this window is penalised — default `[9, 18]` |
| `immovable_keywords` | Event-title substrings that block rescheduling — default `[]` |
| `high_priority_keywords` | Event-title substrings that raise priority — default `[]` |
| `vip_domains` | Attendee-email domains that lift priority — default `[]` |
| `domain_timezones` | Email domain → IANA timezone override — default `{}` |
| `max_moves_per_request` | Cap on existing events the engine may propose rescheduling — default `2` |

## State machine

A scheduling request moves through:
`PROPOSING → OWNER_REVIEW → POLLING → CONVERGED → BOOKED`
with branches to `BACKCHANNEL` (move existing events), `EXPIRED`, or `CANCELLED`.

Illegal transitions raise `InvalidTransition`; the state is persisted in SQLite so restarts are safe.
