"""Stage 2: turn candidate items into a digest via one streamed model call."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cosinabox import defaults
from cosinabox.agent.failover import call_with_failover_stream
from cosinabox.research.config import ResearchConfig

logger = logging.getLogger(__name__)

# Callers match on this to tell a failed run from a genuinely quiet week.
# Don't reword it in one place only.
SYNTHESIS_FAILED_NOTICE = "Research digest: synthesis failed — check logs."

_REQUIRED_KEYS = ("telegram_summary", "full_report", "signal_records", "follow_up_signals")

_PROMPT = """You are compiling a weekly research digest for the week of {week_of}.

Tracked entities:
{entities}

Already reported in recent weeks — do NOT repeat these:
{dedup_index}

Candidate items collected this week:
{candidates}

Return ONLY a JSON object with exactly these keys:
- "telegram_summary": a short plain-text summary, at most 1200 characters.
- "full_report": a markdown report.
- "signal_records": a list of objects, each with "headline", "source_url",
  "entity", and "why_it_matters".
- "follow_up_signals": a list of short strings naming things worth a deeper look.

Rules:
- Use ONLY the candidate items above. Never invent a fact, a date, or a URL.
- If nothing meaningful happened, say so plainly and return an empty
  "signal_records" list. A quiet week is a valid outcome.
"""


def format_candidates(items: list[dict[str, Any]]) -> str:
    """Render collected items as the prompt's data block."""
    if not items:
        return "No candidates were collected this week."
    blocks = []
    for item in items:
        date = f" ({item.get('published')})" if item.get("published") else ""
        blocks.append(
            f"[{item.get('source', 'unknown')}]{date} {item.get('title', '')}\n"
            f"{item.get('snippet', '')}\n{item.get('url', '')}"
        )
    return "\n\n".join(blocks)


def build_prompt(
    cfg: ResearchConfig,
    *,
    candidates: str,
    dedup_index: list[dict[str, Any]],
    week_of: str,
) -> str:
    entities = "\n".join(
        f"- {e.name}" + (f" (aliases: {', '.join(e.aliases)})" if e.aliases else "")
        for g in cfg.groups
        for e in g.entities
    )
    if dedup_index:
        index = "\n".join(f"- {i.get('headline', '')} ({i.get('url', '')})" for i in dedup_index)
    else:
        index = "(Nothing yet — this is the first run.)"
    return _PROMPT.format(
        week_of=week_of, entities=entities, dedup_index=index, candidates=candidates
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    for candidate in (
        text.strip(),
        *[
            m.group(1).strip()
            for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        ],
        *([m.group()] if (m := re.search(r"\{[\s\S]*\}", text)) else []),
    ):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _salvage_truncated(text: str) -> dict[str, Any] | None:
    """Recover the fields of a JSON object that was cut off mid-write.

    A response cut short still carries every field it finished — the summary,
    the report, some signals — and a strict parse throws all of it away. Walk
    the text tracking string/escape state, find the last point where a
    top-level pair completed, and close the object there.
    """
    start = text.find("{")
    if start == -1:
        return None

    stack: list[str] = []
    in_string = False
    escaped = False
    last_safe: int | None = None

    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
        elif in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if len(stack) == 1:  # closed a value directly under the root
                last_safe = i + 1
        elif ch == "," and len(stack) == 1:
            last_safe = i

    if last_safe is None:
        return None
    try:
        result: dict[str, Any] = json.loads(text[start:last_safe].rstrip(", ") + "}")
    except json.JSONDecodeError:
        return None
    return result


def parse_response(text: str) -> dict[str, Any]:
    """Parse the synthesis JSON, salvaging a truncated object before giving up."""
    parsed = _extract_json(text)
    if not parsed:
        parsed = _salvage_truncated(text)
        if parsed:
            logger.warning("Synthesis response was truncated; salvaged: %s", sorted(parsed))

    if not parsed:
        logger.error("Could not parse synthesis response: %s", text[:200])
        return {
            "telegram_summary": SYNTHESIS_FAILED_NOTICE,
            "full_report": f"Raw response:\n{text}",
            "signal_records": [],
            "follow_up_signals": [],
        }

    for key in _REQUIRED_KEYS:
        if key not in parsed:
            parsed[key] = [] if key in ("signal_records", "follow_up_signals") else ""
    return parsed


def synthesize(
    cfg: ResearchConfig,
    *,
    items: list[dict[str, Any]],
    dedup_index: list[dict[str, Any]],
    week_of: str,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], str]:
    """Run stage 2 and return `(parsed, raw_text)`.

    `raw_text` is returned so the caller can size the output against the
    ceiling — see `research.alerts.synthesis_alerts`.
    """
    prompt = build_prompt(
        cfg,
        candidates=format_candidates(items),
        dedup_index=dedup_index,
        week_of=week_of,
    )
    raw, used_model = call_with_failover_stream(
        client,
        model,
        system=None,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=defaults.RESEARCH_SYNTHESIS_MAX_TOKENS,
        tools=None,
    )
    logger.info("Synthesis completed on %s (%d chars)", used_model, len(raw))
    return parse_response(raw), raw
