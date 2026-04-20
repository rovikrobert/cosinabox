# Consult endpoint

An optional way to let **other AI tools** talk to your CoS.

## What consult is

Consult exposes your CoS over the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Another AI tool — Claude Code, an MCP-aware editor, or any MCP client — can call `consult(prompt)` and get back a grounded answer informed by your stored memory and stated priorities. **No tools fire** during a consult call. No email sent, no calendar written, no memory mutated. It is pure reasoning over the context your CoS has accumulated.

Think of it as: "ask my CoS what it thinks" from outside Telegram.

## When to use it

- **Design reviews** — "Here's the architecture I'm considering. What would my CoS say?"
- **Prioritization** — "Should I focus on X or Y this week?"
- **Adversarial stress-testing** — run the `brainstorm` tool to get pushback, not validation.
- **Second-opinion from inside Claude Code** — you're pairing with Claude Code, and you want a take grounded in your own stakes rather than generic reasoning.

## When NOT to use it

Anything that needs a tool call. Examples that will NOT work through consult:

- Reading email, searching Gmail, scheduling a meeting.
- Writing to memory ("remember that I told this stakeholder…").
- Firing a job (morning briefing, follow-up reminder).
- Creating a commitment or checking off a past one.

For those, talk to the Telegram bot or start a `cosinabox run` session. Consult is read-only reasoning by design.

## Two modes

Consult exposes two MCP tools. The descriptions below are what MCP clients see:

### `consult`
> Ask the configured Chief of Staff agent for grounded reasoning on a question. Returns a direct answer informed by the user's stored memory and stated priorities. No side effects — the agent does not call tools in this mode. Use for design reviews, prioritization questions, or any time you want a thoughtful take grounded in the user's own context.

Use this as the default. The agent answers directly, grounded in your personality, stakes, and recalled memory.

### `brainstorm`
> Ask the Chief of Staff agent to argue adversarially against your framing. Use this when you want your assumptions stress-tested, not validated. Returns a direct answer written from a skeptical stance. No side effects — the agent does not call tools in this mode.

Use this when you catch yourself looking for validation. Brainstorm mode is tuned to disagree, find the weak assumption, and prefer uncomfortable truths over agreement.

## How to enable

### 1. Install the optional extra

```bash
pip install 'cosinabox[consult]'
```

Consult ships as an optional extra because it pulls in the `mcp` SDK, which not every user needs. Without the extra, `cosinabox consult-serve` prints a clear error and exits — the rest of the engine keeps working.

### 2a. Local (stdio) — recommended for Claude Code on your laptop

Stdio transport spawns the server as a subprocess of the MCP client. No network surface, no API key, no auth — trust comes from the parent process. This is the default and the safest option.

**Easiest path — `claude mcp add`:**

```bash
claude mcp add cosinabox --scope user -- cosinabox -C /path/to/your/cos-repo consult-serve
```

**Alternative — project-scoped `.mcp.json`** in whatever repo you want `cosinabox` to be available from:

```json
{
  "mcpServers": {
    "cosinabox": {
      "command": "cosinabox",
      "args": ["-C", "/path/to/your/cos-repo", "consult-serve"]
    }
  }
}
```

Restart Claude Code after either approach. The `consult` and `brainstorm` tools should show up.

### 2b. Remote (HTTP) — for pairing over the network

HTTP transport exposes a network endpoint. It requires a shared secret (`CONSULT_API_KEY`) and enforces Bearer authentication. An unauthenticated HTTP transport will refuse to start — that is by design.

Set the key in `.env`:

```bash
CONSULT_API_KEY=<generate a long random string>
```

Start the server:

```bash
cosinabox consult-serve --transport http --bind 0.0.0.0:8080
```

Point your MCP client at `http://<host>:8080` with the Bearer token.

**Note on `--bind`:** the current CLI parses `host:port` and supports **IPv4 only**. IPv6 bracket syntax (e.g., `[::1]:8080`) is not supported in this version. If you need IPv6, bind to an IPv4 interface and front the endpoint with a reverse proxy or tunnel that handles IPv6.

## Tradeoffs

### Enabling consult gets you
- External AI tools can reach your CoS. Offload strategic reasoning from Claude Code (or any MCP client) to your personally-tuned CoS without retyping context.
- A second pair of eyes that already knows your stakes.

### Leaving consult off costs you
- Your CoS is only reachable through your Telegram bot (if you have one) or `cosinabox run`. Nothing else breaks. You can enable it later with no migration.

### HTTP transport, specifically
- Adds a network surface. Treat `CONSULT_API_KEY` like any other secret: long, random, in `.env`, never committed.
- **No rotation CLI in this version.** If the key leaks, generate a new one, update `.env`, restart the server, and update every MCP client that had the old one.

### Cost
- Every consult call hits the Anthropic API. Default rate limit is **30 calls/hour** (see `CONSULT_RATE_LIMIT_PER_HOUR` in the engine's `defaults.py`). A stray loop in an MCP client calling `consult()` repeatedly could otherwise cost several dollars before anyone noticed — the rate limit is the backstop, not a budget.

## Customizing brainstorm mode

Brainstorm mode ships with a generic adversarial prompt. You can override it with a line in `personality.md`'s frontmatter:

```yaml
---
schema_version: 2
name: <YOUR NAME>
role: <YOUR ROLE>
timezone: <YOUR TIMEZONE>
consult_brainstorm_override: "Argue against me from an engineering risk perspective."
---
```

Rules:
- Must be a string. Leave the key blank or omit it entirely to use the engine default.
- Keep it sharp. "Argue against me" beats "consider alternatives."
- Applies only to the `brainstorm` tool. The default `consult` tool is unaffected.

## What you'll see in `cosinabox describe`

After you've made at least one consult call today, `cosinabox describe` shows:

```
Consult: 12 calls today, $0.31, avg 1400ms latency
```

If the `consult` extra isn't installed, the section is omitted entirely — no noise for users who aren't using the feature.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `CONSULT_API_KEY must be set` on HTTP start | Set it in `.env` and reload, or `export CONSULT_API_KEY=...` in the current shell. |
| `consult-serve requires the 'consult' extra` | `pip install 'cosinabox[consult]'` |
| Tool calls silently return an error / stop working | You may be rate-limited. Run `cosinabox describe`. If `calls_today` stopped rising and `avg_latency_ms` dropped to 0, you hit the hourly cap. Wait, or bump `CONSULT_RATE_LIMIT_PER_HOUR` in engine defaults. |
| Claude Code doesn't see the tools after stdio config | Check `command` resolves on your PATH (try `which cosinabox`). Absolute paths work and are a safer default than relying on PATH. |
| HTTP 401 from the MCP client | Bearer token mismatch. Confirm the client sends `Authorization: Bearer <CONSULT_API_KEY>` and the value matches `.env` exactly. |

## See also

- `docs/agent/safety.md` — non-negotiable rules; consult inherits them.
- `personality.md` — the source of your CoS's voice, which consult reasons from.
