# CoSinaBox Plan 2 — rovik-keevs Migration Design

**Date:** 2026-04-12
**Goal:** Dogfood cosinabox by building the rovik-keevs private user repo, running all 5 built-in jobs in shadow mode against real data for 7 days, then cutting over from cos-agent's scheduled jobs.

**Non-goals:** Replacing cos-agent's conversational interface (Telegram DM), WhatsApp, commitments (Postgres), intel tracking, sub-agents (Mira/Rela), or policy engine. Those stay on cos-agent.

---

## Strategy: Shadow Mode

cosinabox reads the same Gmail, Calendar, and Attio that cos-agent reads. It produces its own briefings and sends them to a staging Telegram chat (separate bot, separate chat). cos-agent is untouched. After 7 days with no bugs, cutover: switch cosinabox to the real chat, disable cos-agent's 5 scheduled jobs.

**No data migration.** cosinabox starts fresh — no conversation history, no cost logs, no memory service. Personality comes from SOUL.md, stakeholder data comes from Attio.

---

## Workstream A: Engine Changes — Attio Integration

### A1. Attio as optional engine integration

New optional dependency: `cosinabox[attio]` (uses httpx, already a dep via `cosinabox[fireflies]`).

New module: `src/cosinabox/tools/attio.py`

**Operations:**

| Operation | Method | Used by |
|-----------|--------|---------|
| List people | `list_people(limit, filters)` | morning_briefing, followup_reminder, describe |
| Get person | `get_person(name)` | pre_meeting_prep (attendee lookup) |
| Search people | `search_people(query)` | morning_briefing (names in emails) |
| Update person | `update_person(id, fields)` | followup_reminder (last_interaction) |
| Create person | `create_person(fields)` | interview step 4 (when Attio enabled) |

All operations require `ATTIO_API_KEY` env var.

**integrations.yaml schema addition:**

```yaml
attio:
  enabled: true
```

When `attio.enabled` is true and `ATTIO_API_KEY` is set, the stakeholder resolver uses Attio. Otherwise falls back to `stakeholders.yaml`.

### A2. Stakeholder resolver

New module: `src/cosinabox/stakeholders.py`

```python
def get_stakeholders(config_dir, integrations, read_only=False):
    if attio_enabled(integrations) and attio_api_key_set():
        return attio.list_people(...)
    return load_stakeholders_yaml(config_dir)
```

Jobs call the resolver, never Attio or YAML directly. The resolver:
- Checks `integrations.yaml` for `attio.enabled`
- Checks env for `ATTIO_API_KEY`
- On Attio API failure (timeout, auth, rate limit): falls back to `stakeholders.yaml`, logs warning
- Accepts `read_only` flag — when True, `update_person` and `create_person` are no-ops
- Read-only controlled by env var `COSINABOX_ATTIO_READ_ONLY=true`

**Attio field mapping:**

| cosinabox concept | Attio field |
|---|---|
| name | person.name |
| role | person.title + person.company |
| cadence | custom attribute (if available on free tier) or notes |
| last_interaction | last_interaction (built-in) |
| notes | person.description |
| relationship_strength | strongest_connection_strength (built-in) |

### A3. stakeholders.yaml stays as fallback

Not removed, not deprecated. The engine ships with 4 config files. Users without a CRM use stakeholders.yaml exactly as before. Users with Attio never touch the file.

`stakeholders.schema.json`, `add-stakeholder` CLI, doctor checks — all unchanged. They operate on the YAML file. When Attio is enabled, the YAML file is irrelevant but still valid.

### A4. integrations.yaml schema update

Add `attio` to the schema:

```json
"attio": {
  "type": "object",
  "required": ["enabled"],
  "properties": {
    "enabled": {"type": "boolean"}
  }
}
```

### A5. Job modifications

Each of the 5 built-in jobs that references stakeholders changes from:
```python
stakeholders = yaml.safe_load((config_dir / "stakeholders.yaml").read_text())
```
to:
```python
from cosinabox.stakeholders import get_stakeholders
stakeholders = get_stakeholders(config_dir, integrations, read_only=read_only)
```

Affected jobs: `morning_briefing`, `followup_reminder`, `pre_meeting_prep`, `weekly_review`, `evening_wrap`.

### A6. Dual Google account support

`integrations.yaml` supports multiple accounts:

```yaml
google:
  enabled: true
  accounts:
    - email: rovik@majiq.agency
      scopes: [gmail, calendar]
    - email: rovik@cantina.ai
      scopes: [gmail, calendar]
```

Each account has its own refresh token env var: `GOOGLE_OAUTH_REFRESH_TOKEN_1`, `GOOGLE_OAUTH_REFRESH_TOKEN_2` (or named variants like `_MAJIQ`, `_CANTINA`).

`GmailTool.list_recent()` and `CalendarTool.upcoming_events()` iterate all enabled accounts, merge results, and deduplicate by message ID / event ID.

**If the M1 code already supports multiple accounts:** No changes needed — just configure.
**If it doesn't:** Modify the tools to iterate `integrations["google"]["accounts"]`.

### A7. Interview step 4 adaptation

When Attio is enabled, interview step 4 ("top stakeholders") offers two paths:
- "I see Attio is enabled. Want me to pull your existing contacts, or add new ones?"
- If pulling: `attio.list_people()`, show top 5 by relationship_strength, confirm
- If adding: `attio.create_person()` for each entry (respects read_only flag)

When Attio is not enabled: writes to `stakeholders.yaml` as before.

### A8. describe command adaptation

`cosinabox describe` shows stakeholders from whichever source is active:
- Attio enabled: "Stakeholders (from Attio): Sarah Chen (weekly), ..."
- Attio disabled: "Stakeholders (from stakeholders.yaml): ..."

### A9. Doctor check adaptations

- `stakeholders_empty`: When Attio enabled, checks Attio person count instead of YAML entries
- `stale_followups`: When Attio enabled, reads last_interaction from Attio instead of YAML last_contact

Both fall back to YAML checks when Attio is not enabled. No behavioral change for non-Attio users.

---

## Workstream B: rovik-keevs User Repo

### B1. Repository setup

```
rovik-keevs/                    # private repo, GitHub
├── personality.md              # from SOUL.md
├── stakeholders.yaml           # example entry (unused — Attio enabled)
├── jobs.yaml                   # all 5 enabled
├── integrations.yaml           # google (2 accounts) + attio
├── .env                        # staging bot, both Google tokens, Anthropic, Attio
├── .env.example
├── main.py                     # from cosinabox init
├── pyproject.toml              # cosinabox[google,attio]
├── Dockerfile
├── .gitignore
├── CLAUDE.md
├── BEST_PRACTICES.md
├── docs/agent/
├── .cosinabox/
└── custom_jobs/                # empty until M3
```

### B2. personality.md

Adapted from `/Users/rovikrobert/Cantina/cos-agent/SOUL.md`:

```yaml
---
schema_version: 1
name: Rovik
role: GM at Cantina AI Singapore
timezone: Asia/Singapore
---
```

Voice section: Direct, collegial, no filler, no markdown bold in Telegram, relationship intelligence, balanced realism. Stakes section: current 6-week priority (filled at setup time).

### B3. jobs.yaml

```yaml
schema_version: 1
jobs:
  morning_briefing:
    enabled: true
    schedule: "0 8 * * *"
    timezone: Asia/Singapore
  evening_wrap:
    enabled: true
    schedule: "0 18 * * *"
  pre_meeting_prep:
    enabled: true
    minutes_before: 30
    skip_if_calendar_title_matches: ["focus block", "lunch"]
  weekly_review:
    enabled: true
    schedule: "0 16 * * 5"
  followup_reminder:
    enabled: true
```

### B4. integrations.yaml

```yaml
schema_version: 1
integrations:
  google:
    enabled: true
    accounts:
      - email: rovik@majiq.agency
        scopes: [gmail, calendar]
      - email: rovik@cantina.ai
        scopes: [gmail, calendar]
  attio:
    enabled: true
  fireflies:
    enabled: false
  web_search:
    enabled: false
```

### B5. .env (staging)

```bash
ANTHROPIC_API_KEY=<from cos-agent>
TELEGRAM_BOT_TOKEN=<new staging bot from BotFather>
TELEGRAM_CHAT_ID=<staging chat id>
GOOGLE_OAUTH_REFRESH_TOKEN_1=<majiq token from cos-agent>
GOOGLE_OAUTH_REFRESH_TOKEN_2=<cantina token from cos-agent>
GOOGLE_OAUTH_CLIENT_ID=<from cos-agent credentials.json>
GOOGLE_OAUTH_CLIENT_SECRET=<from cos-agent credentials.json>
ATTIO_API_KEY=<from cos-agent .env>
COSINABOX_ATTIO_READ_ONLY=true
```

### B6. Deployment

Separate Railway project from cos-agent. GitHub repo `rovikrobert/rovik-keevs`, auto-deploy on main merge. PR-only deploy discipline.

### B7. Shadow run protocol

- Duration: 7 days
- All 5 jobs fire to the staging Telegram chat
- Attio is read-only (no writes during shadow)
- Daily check: compare cosinabox briefing with cos-agent briefing
- Success: 7 days, no crashes, briefings are correct (may be less detailed than cos-agent — that's expected and OK)
- Manual override: cut over early if obviously good, extend if issues found

---

## Workstream C: Cutover + Post-Cutover Enrichment

### C1. Cutover procedure (10 minutes)

1. cos-agent: disable the 5 scheduled jobs (leave everything else)
2. rovik-keevs `.env`: swap staging bot token/chat_id for real Keevs bot values
3. rovik-keevs `.env`: set `COSINABOX_ATTIO_READ_ONLY=false`
4. Merge + deploy rovik-keevs
5. Confirm next scheduled job arrives in real chat

**Rollback:** Re-enable cos-agent's 5 jobs, revert rovik-keevs to staging values. 5 minutes.

### C2. Post-cutover enrichment

After cutover, close the quality gap with cos-agent:

1. **Standing orders prompt overlay** — `prompts/system.md` in rovik-keevs injecting autonomy tiers (autonomous, draft+confirm, always-require-approval) into system prompt
2. **Web search custom tool** — `custom_jobs/tools/serper.py` wrapping Serper API. Enable in integrations.yaml.
3. **Quality tuning** — After 1 week production, review gaps. Likely: memory service context, richer email summarization, Fireflies transcripts. Each becomes a discrete improvement ticket.

### C3. What stays on cos-agent

- Telegram DM handling (conversational interface)
- WhatsApp interface
- Commitments tracking (Postgres)
- Intel signals (Asia Lab Tracker)
- Sub-agents (Mira, Rela)
- Policy engine
- Webhook ingestion
- Memory service

These migrate only if/when cosinabox engine grows to support them.

---

## Testing Strategy

### Engine tests (Workstream A)

- `test_attio_client.py` — mock HTTP, verify list/get/search/update/create
- `test_stakeholder_resolver.py` — Attio enabled: returns Attio data. Attio disabled: returns YAML. Attio fails: falls back to YAML.
- `test_attio_read_only.py` — read_only=True: writes are no-ops
- Modify existing job tests to verify they call resolver, not YAML directly
- Existing stakeholders.yaml tests unchanged (they test the YAML path)
- `test_dual_google_accounts.py` — if engine changes needed

### Integration tests (Workstream B)

- `test_e2e_with_attio.py` — init → configure Attio → describe shows Attio stakeholders
- Shadow run itself is the integration test — 7 days of real data

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Attio free tier blocks writes | Medium | High | Verify API before implementing. If blocked, writes deferred to paid tier upgrade. |
| Dual Google tokens don't refresh | Low | High | Test token refresh before shadow. Both tokens are already refreshing in cos-agent. |
| Briefings noticeably worse without memory service | High | Medium | Expected. This is signal, not a bug. Track gaps for Plan 3. |
| Shadow mode Attio reads hit rate limit | Low | Low | Graceful fallback to stakeholders.yaml. |
| cos-agent and cosinabox schedule overlap | Low | Medium | Jobs run at same cron times but different bots/chats. No conflict. |

---

## Milestones

| Milestone | Scope | Done when |
|-----------|-------|-----------|
| M1 | Engine: Attio integration + stakeholder resolver + dual Google | Tests pass, `cosinabox describe` shows Attio stakeholders |
| M2 | rovik-keevs: build repo, deploy to Railway, shadow starts | All 5 jobs fire to staging chat |
| M3 | Cutover + enrichment | Real chat receives briefings, standing orders + web search added |

**Estimated effort:** M1 ~8 hours, M2 ~4 hours, M3 ~4 hours.
