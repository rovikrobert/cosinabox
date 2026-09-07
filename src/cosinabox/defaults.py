"""Encoded operational defaults — every magic number lives here.

Each constant has a comment explaining the lesson and the date it was
chosen, per spec Layer 1. Revisit annually.
"""

from __future__ import annotations

# Cost runaways are real. Per-message + daily caps are forcing functions.
# $0.75/message handles most DM queries including multi-tool chains.
# $15/day covers ~5 briefings + 20 DM messages + pre-meeting preps.
# Light users (few DMs, just briefings): ~$3-5/day.
# Heavy users (active DM, all jobs enabled): ~$10-15/day.
# Chosen 2026-04-11 from cos-agent's empirical spend.
COST_PER_MESSAGE_CAP_USD: float = 0.75
COST_DAILY_CAP_USD: float = 15.00

# Tool loops can blow up if the model keeps calling tools forever.
# 8 is the cos-agent observed median + headroom. (2026-04-11)
MAX_TOOL_ITERATIONS: int = 8

# Anthropic rate limits hit on heavy briefing jobs. 2s between iterations
# kept cos-agent under the limit. (2026-04-11)
TOOL_ITERATION_DELAY_S: float = 2.0

# Long contexts degrade quality and burn money. >25 messages = compress.
# (2026-04-11)
CONVERSATION_SUMMARIZE_THRESHOLD: int = 25
CONVERSATION_SUMMARIZE_KEEP_RECENT: int = 10

# Stale data accumulates. Auto-cleanup after 30 days. (2026-04-11)
CONVERSATION_RETENTION_DAYS: int = 30

# Pre-meeting prep needs a window. Fire when an event is 25-35 min out.
# (2026-04-11)
PRE_MEETING_PREP_MINUTES_BEFORE: int = 30
PRE_MEETING_PREP_WINDOW_MINUTES: int = 5  # ±5 min around minutes_before

# Follow-up staleness threshold. (2026-04-11)
FOLLOWUP_STALENESS_DAYS: int = 14

# Doctor thresholds.
DOCTOR_PERSONALITY_MIN_CHARS: int = 500
DOCTOR_STAKEHOLDERS_MIN_AFTER_DAYS: int = 7
DOCTOR_STAKEHOLDERS_MIN_COUNT: int = 3
DOCTOR_COST_RUNAWAY_RATIO: float = 0.80
DOCTOR_TOOL_LOOP_AVG_THRESHOLD: float = 6.0
DOCTOR_PREP_NOISE_PER_DAY: int = 8
DOCTOR_STALE_FOLLOWUP_COUNT: int = 20
DOCTOR_OAUTH_EXPIRY_WARN_DAYS: int = 14

# Default timezone. Overridden by personality.md frontmatter or runtime /timezone command.
# (2026-04-12)
DEFAULT_TIMEZONE: str = "UTC"

# Default model IDs (re-exported from agent.routing for convenience).
SONNET_MODEL_ID: str = "claude-sonnet-4-6"
OPUS_MODEL_ID: str = "claude-opus-4-6"

# API failover chain. On 429/529/overloaded, the agent walks this list
# from the requested model forward. Chosen 2026-04-11 (originally in
# cos-agent) — Opus for strategy, Sonnet as workhorse, Haiku as the
# last-resort reply-with-something model. Ported to cosinabox 2026-04-17.
MODEL_FAILOVER_CHAIN: tuple[str, ...] = (
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
)

# Advisor tool: Sonnet executor + Opus advisor (beta API).
# When enabled, strategic prompts route to Sonnet + advisor instead of Opus.
# (2026-04-12)
ADVISOR_ENABLED: bool = True
ADVISOR_MAX_USES: int = 2

# Personal-block title patterns that short-circuit pre-meeting prep and
# post-meeting debrief jobs. These are "not a real meeting" signals — the
# calendar entry exists to block time, not to convene with others. Matched
# as case-insensitive substrings. Users can extend via per-job `skip_titles`
# in integrations.yaml. (2026-04-18 — triggered by a 22:30 "Decompress" block
# generating a full prep brief.)
DEFAULT_PERSONAL_BLOCK_PATTERNS: frozenset[str] = frozenset(
    {
        "decompress",
        "focus",
        "deep work",
        "lunch",
        "break",
        "commute",
        "gym",
        "workout",
        "block",
        "hold",
        # Travel blocks: "Flight", "Flights", "Flight to SFO". Personal
        # time, not prep-worthy. Substring match; see note above.
        # (2026-04-20 — added after long briefs on travel events.)
        "flight",
    }
)

# Auto-resolve verifier knobs. Gmail rate limits kick in above ~5 concurrent
# reads; 8-second per-item cap so one slow search doesn't block the rest.
# Lookback is 7 days — long enough to catch the common "done yesterday"
# case, short enough to avoid treating last-month's thread as fresh
# evidence. (2026-04-19, ported from cos-agent.)
AUTO_RESOLVE_LOOKBACK_DAYS: int = 7
AUTO_RESOLVE_CONCURRENCY: int = 5
AUTO_RESOLVE_TIMEOUT_PER_ITEM_S: int = 8
AUTO_RESOLVE_MAX_ITEMS: int = 20

# Keep Warm default cadence when a person is flagged without a specific
# cadence_days value. 14 days matches cos-agent. Users override per-person
# via set_keep_warm. (2026-04-20, ported from cos-agent.)
KEEP_WARM_DEFAULT_CADENCE_DAYS: int = 14
# Briefings cap at 10 overdue rows so a quiet week doesn't crowd out
# other signals when something slipped a month ago.
KEEP_WARM_MAX_BRIEFING_ROWS: int = 10
# keep_warm_review output cap. 20 rows fits a typical chat-review budget
# (~30 rendered lines including header/footer); overflow is surfaced as
# "... and N more. Re-run after cleaning these." so the agent can iterate.
# (2026-04-22 — moved from tools/registry.py after post-PR review flagged
# it as a magic number in business logic, per CLAUDE.md rule 3.)
KEEP_WARM_REVIEW_MAX_ROWS: int = 20

# Fireflies transcripts and calendar events drift by ~minutes due to clock
# skew and meeting-end vs transcript-creation timing. +/-30min covers most
# real cases without allowing back-to-back meetings to cross-match.
# (2026-04-17 — added when fixing cross-matched debrief transcripts.)
TRANSCRIPT_TIME_WINDOW_SECONDS: int = 30 * 60

# Title-word overlap ignores tokens shorter than this. Room numbers,
# headcounts and stopwords ("of", "go", "10") carry no topic signal, so
# matching on them would cross-pair adjacent meetings. Letter+digit tokens
# ("q3", "v2") are exempt — see _title_tokens in jobs/post_meeting_debrief.
# (2026-08-20 — moved from an inline `len(w) > 2` when a debrief missed its
# own transcript because the only word the two titles shared was 2 chars.)
TRANSCRIPT_TITLE_MIN_TOKEN_CHARS: int = 3

# --- Consult (MCP endpoint) ---
# 2026-04-20 — per cos-agent precedent; one stray Cowork/Claude Code loop
# calling consult() in a tight loop shouldn't rack up $40 before the owner
# notices. 30/hour = ~$0.02 average cost per call × 30 = under $1/hr worst-case.
CONSULT_RATE_LIMIT_PER_HOUR: int = 30
# 2026-04-20 — same as cos-agent; guards against pathological inputs (e.g.,
# accidentally pasting a whole codebase into the prompt field).
CONSULT_MAX_PROMPT_CHARS: int = 10_000
# 2026-04-20 — Sonnet is the consult default. Brainstorm mode routes via the
# agent Router, which may pick Opus for strategic prompts. Uses the symbolic
# SONNET_MODEL_ID so a future model bump is a single-line change.
CONSULT_DEFAULT_MODEL: str = SONNET_MODEL_ID
# 2026-04-20 — cos-agent sends 4096; plenty for a no-tool reasoning reply.
# Consult responses are expected to be a few paragraphs, not long-form docs.
CONSULT_MAX_TOKENS: int = 4096
# 2026-04-20 — engine default for brainstorm mode. Overridable per persona via
# personality.md:consult_brainstorm_override. Phrasing is OSS-safe (no names)
# and matches cos-agent's adversarial framing.
CONSULT_BRAINSTORM_OVERRIDE_DEFAULT: str = (
    "You are now in adversarial brainstorm mode. Argue against the user's framing. "
    "Surface the weakest assumption. Prefer uncomfortable truths over validation. "
    "Do not agree unless the user's position is genuinely strong."
)

# Auth-health watcher cadence. Every 15 min is short enough that a revoked
# refresh token surfaces within a meeting-length window, and long enough
# that we don't hammer Google's token endpoint. Chosen 2026-04-17 after a
# revoked token looped `invalid_grant` silently for days. See
# docs/specs/2026-04-17-auth-health-watcher-design.md.
AUTH_HEALTH_DEFAULT_SCHEDULE: str = "*/15 * * * *"

# Dead-man's-switch cadence. Hourly is frequent enough that even the
# slowest thing it can catch is reported the same day it goes missing, and
# cheap enough to ignore — the check is two indexed SQLite reads per
# registered job, no network. Deliberately not tied to the shortest job's
# period: the watchdog measures staleness against each job's own cadence,
# so it need not run as often as the jobs it watches.
JOB_WATCHDOG_DEFAULT_SCHEDULE: str = "0 * * * *"

# --- Research digest ---
# Search-backend defaults for a group that omits its own `search:` block.
# "general" + no time window is the safe default: it never silently narrows a
# user's query. Groups that want fresh announcements opt into news+week, which
# is what the legacy tracker needed to stop missing dated releases.
# (2026-08-20 — ported from cos-agent's intel collector.)
RESEARCH_SEARCH_COUNTRY: str = "us"
RESEARCH_SEARCH_TOPIC: str = "general"
RESEARCH_RESULTS_PER_QUERY: int = 5

# Feed items and search results whose title/summary mentions no tracked term
# are dropped. Terms shorter than this match too much ("AI", two-char CJK
# aliases), so they are excluded from the filter set.
# (2026-08-20 — ported; the legacy collector used the same floor.)
RESEARCH_MIN_TRACKED_TERM_CHARS: int = 3

# Hard cap on candidates handed to synthesis. Sized for the synthesis prompt's
# token budget, not for completeness — beyond this, extra candidates cost
# tokens without changing the digest. Items are dropped lowest-priority-first
# so a large noisy group cannot displace a targeted one.
# (2026-08-20 — ported; the legacy cap silently sliced off an entire region's
# results for eleven weeks because it capped in append order instead.)
RESEARCH_MAX_CANDIDATES: int = 120

# Concurrent search requests. The backend rate-limits, and the legacy
# implementation ran queries strictly sequentially for that reason; a small
# pool is a measured relaxation, not a free-for-all.
# (2026-08-20)
RESEARCH_MAX_WORKERS: int = 4

# Feed items older than this are ignored — the digest is weekly, so a month-old
# post is not news. (2026-08-20 — ported.)
RESEARCH_FEED_MAX_AGE_DAYS: int = 7

# The relevance pre-pass runs on the cheapest model: it answers one narrow
# question ("is this item about a tracked entity?") thousands of times, and
# using the synthesis model for it costs roughly 20x for no gain.
# (2026-08-20 — ported from cos-agent's intel classifier.)
RESEARCH_CLASSIFIER_MODEL: str = "claude-haiku-4-5-20251001"
RESEARCH_CLASSIFIER_MAX_TOKENS: int = 2048

# Streamed synthesis ceiling. Generous on purpose: the call streams, so a high
# ceiling costs nothing unless the model actually uses it, whereas a low one
# silently truncates a long structured response mid-object.
# (2026-08-20 — the legacy non-streaming call capped at 16000 and cut two
# weekly digests off at ~56k characters.)
RESEARCH_SYNTHESIS_MAX_TOKENS: int = 32_000

# Warn when output reaches this share of the ceiling. Legacy output crept
# 33k -> 49k chars over four weeks before the first truncation; a warning at
# 80% turns the next one into a heads-up instead of a lost digest.
RESEARCH_SYNTHESIS_WARN_RATIO: float = 0.8

# Observed characters per output token for this JSON shape, used to convert the
# token ceiling into the character budget the alert compares against.
RESEARCH_SYNTHESIS_CHARS_PER_TOKEN: float = 3.6

# Rolling database backups kept on disk. The store holds primary data —
# research signals, commitments, autonomy history — on a single volume, so a
# volume loss with no copy is unrecoverable. Seven daily-ish copies is a week
# of runway at a few MB each. (2026-08-20)
MEMORY_BACKUP_KEEP: int = 7
