"""Encoded operational defaults — every magic number lives here.

Each constant has a comment explaining the lesson and the date it was
chosen, per spec Layer 1. Revisit annually.
"""

from __future__ import annotations

# Cost runaways are real. Per-message + daily caps are forcing functions.
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

# Default model IDs (re-exported from agent.routing for convenience).
SONNET_MODEL_ID: str = "claude-sonnet-4-6"
OPUS_MODEL_ID: str = "claude-opus-4-6"

# Advisor tool: Sonnet executor + Opus advisor (beta API).
# When enabled, strategic prompts route to Sonnet + advisor instead of Opus.
# (2026-04-12)
ADVISOR_ENABLED: bool = True
ADVISOR_MAX_USES: int = 2
