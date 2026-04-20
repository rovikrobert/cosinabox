# Scope: `consult` — OSS consult MCP endpoint

**Date:** 2026-04-20
**Status:** Scope (pre-plan). Open questions → resolve before writing the plan.
**Cutover tag:** **port** (from `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md`, row for `consult`).
**Source of truth:** `~/code/cos-agent/src/consult.py` (230 lines).

## Why this is a scope doc, not a plan

The cutover inventory called consult an "advisor tool — 2 imports — cost-effective strategic reasoning" and estimated it as a small port. On inspection, it's a **full HTTP server endpoint** that exposes the CoS as an MCP server for external AI tools (Claude Code, Cowork) to consult. Scope includes:

- HTTP surface (FastAPI route).
- Auth (API-key + HMAC).
- Rate limiting (in-memory, per-hour).
- Metrics collection (in-memory, daily reset).
- A lean Claude call (no tools, just system prompt + memory recall).
- Memory recall integration.
- Brainstorm mode (adversarial-override prompt).

For an OSS engine the shape isn't just "port the code" — it's "what does 'expose your CoS as an MCP server' mean in the cosinabox deployment model?" That's a product question, not a translation. This doc lays the question out so the plan can be tight.

## What cos-agent's consult does

**Inbound:** an HTTP `POST /api/consult` call from Claude Code Cowork.

**Payload:**
```json
{
  "prompt": "What's the risk of prioritizing X over Y?",
  "context": "From Cowork session: we're mid-design-review for feature X...",
  "mode": "consult" | "brainstorm",
  "timestamp": "2026-04-20T10:00:00Z",
  "signature": "hmac-sha256(api_key, timestamp + prompt)"
}
```

**Processing:**
1. Auth: constant-time API key compare + HMAC over `timestamp + prompt` (replay window: 5 min).
2. Rate limit: reject if `CONSULT_RATE_LIMIT` calls already served in this hour.
3. Memory recall: `memory_service.search(prompt)` for relevant facts.
4. State fetch: current CoS identity context (personality, open commitments, stakeholders).
5. Build system prompt from personality.md + recalled memories + optional brainstorm override.
6. Single Claude API call with **no tools** (`consult` mode: Sonnet hard-coded; `brainstorm`: router picks).
7. Return: `{"text": ..., "cost_usd": ..., "latency_ms": ..., "model": ..., "memory_hits": N}`.

**No side effects.** No DB writes, no tool calls, no email/calendar actions. Pure consultation.

## What the OSS version should be

### Deployment model — 3 options

**Option A: Bolt-on HTTP route on the existing FastAPI app.**
- cosinabox already runs a FastAPI server when the Telegram bot is live.
- Add a `/consult` route behind the same auth the runtime uses for its own webhooks.
- **Pro:** single process, single deployment. Zero new ops surface.
- **Con:** couples MCP availability to the Telegram bot's uptime. Users who run cosinabox only as a cron-driven briefings bot (no server) don't get consult.

**Option B: Separate `cosinabox consult-serve` CLI command.**
- `cosinabox consult-serve --port 8080` starts a dedicated FastAPI server.
- Reuses the same `Memory`, agent loop, system prompt build as the bot.
- **Pro:** users who only want the consult endpoint (no Telegram) can run it standalone.
- **Con:** duplicate deployment target. Docs need to explain two run modes.

**Option C: Native MCP server (stdio/HTTP via `mcp` SDK), not custom HTTP.**
- Use the MCP Python SDK to expose cosinabox as a proper MCP server.
- Claude Code / Cowork connect via MCP, not bespoke POST.
- **Pro:** standard protocol. No custom auth — MCP handles it. Other AI tools can connect too.
- **Con:** biggest delta from cos-agent. MCP server shape is still evolving; may lock us into a protocol that churns.

**Recommendation:** Option C (native MCP). That's the direction the ecosystem is moving and OSS users already know `claude-mcp add`-style workflows. Option A only if we discover MCP SDK has blockers.

### Auth model

**cos-agent:** static API key + HMAC timestamp. Fine for a single-user system the maintainer deploys.

**OSS deployment:** each cosinabox instance is a single user's personal CoS. Same threat model. Options:
- **Shared secret** (env var `CONSULT_API_KEY`) — simplest. Users put the key in both cosinabox's `.env` and Claude Code's MCP config.
- **Bearer token** rotation — overkill for a single-user tool.
- **OS-local socket / unix-domain** for same-machine use — nice for laptop-local Claude Code, but breaks the "run on Railway, consult from laptop" pattern.

**Recommendation:** shared secret. Document rotation steps. Skip rotation automation in v1.

### Rate limiting

cos-agent: 30/hour, in-memory counter. Reasonable.

For OSS: same default, configurable in `defaults.py`. Consult calls cost money (one Claude API call each); a stray tight loop in Claude Code could rack up $40 in an afternoon.

### Metrics

cos-agent tracks `calls_today`, `cost_today_usd`, `avg_latency_ms`. Useful for `/health`.

For OSS: include in the `cosinabox describe` output? Probably yes. And feed into the analytics summary we just ported.

### Brainstorm mode

cos-agent has a second mode (`mode=brainstorm`) that appends an adversarial-override prompt (`BRAINSTORM_OVERRIDE`) and lets the router pick the model (usually Opus). The override tells the model to argue against the user's framing.

For OSS: keep it, but make the override text editable via `personality.md` or a new `consult.yaml` rather than hard-coding in `cosinabox.prompts`. Maintainers of different shapes (founder, researcher, operator) will want different "argue against me" prompts.

## Key open questions

1. **MCP SDK vs raw HTTP.** Which does the OSS Claude Code / Cowork ecosystem expect? If MCP SDK, what's the minimum Python SDK version + does it support streaming?
2. **Deployment target.** Does "running cosinabox" mean "running a web service"? Railway users already do — does Option B (standalone CLI) add real value over Option A?
3. **State coupling.** Consult calls touch memory, personality, (sometimes) commitments. In a process separate from the Telegram bot, do we share SQLite via file-level locking or serialize through a memory-service HTTP endpoint?
4. **Schema churn.** Adding a `consult_logs` table for audit would be nice but adds another migration. Is in-memory metrics enough for v1?
5. **Brainstorm mode scope.** Configurable prompt per persona? Or single "argue with me" prompt in the engine? The former lets researchers customize; the latter is simpler and ships sooner.

## Proposed v1 scope (for the plan)

- **Shape:** MCP server via `mcp` Python SDK (Option C).
- **Deployment:** new `cosinabox consult-serve` CLI (Option B), so non-bot deployments also work. Same process as the bot only if we can't avoid the SQLite locking issue.
- **Auth:** shared secret via `CONSULT_API_KEY` env var.
- **Rate limit:** 30/hour default, configurable.
- **Modes:** `consult` (Sonnet, no-tool) + `brainstorm` (router-picked, no-tool). Engine ships with a default override prompt; personality.md can override via optional `consult_brainstorm_override` key.
- **Metrics:** in-memory + surfaced in `cosinabox describe`.
- **No DB audit log in v1** — add only if users ask.

## Proposed v2+

- Streaming responses.
- Per-consult audit log (`consult_logs` table).
- Token rotation via CLI.
- Running consult as a separate process with shared memory service.

## Total estimate for v1

~14 hours. Rough breakdown:

- **M1** — MCP server skeleton + auth + rate limit: 3h.
- **M2** — Memory recall + personality + brainstorm override wiring: 3h.
- **M3** — Claude API call + cost recording: 2h.
- **M4** — CLI command `cosinabox consult-serve`: 1h.
- **M5** — Tests (auth, rate limit, modes, mocked Claude): 2h.
- **M6** — Docs (user-repo + engine): 2h.
- **M7** — Plan/PR/retro: 1h.

Not a quick port. Worth its own plan doc before kickoff.

## Resolution path

- [ ] User picks A / B / C for deployment. **Default recommendation: Option C (MCP SDK).**
- [ ] User picks auth model. **Default: shared secret.**
- [ ] User confirms scope of v1 (accept / trim / expand).
- [ ] Then: write the executable plan as `docs/plans/2026-0X-XX-port-consult-mcp.md`.
