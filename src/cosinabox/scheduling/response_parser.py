"""Response parsing for group scheduling.

Two parsers:

1. ``parse_callback_data`` — parse a Telegram inline button callback of the
   form ``sched_resp:{request_id}:{participant_db_id}:{slot_id}``. No LLM.
   Returns ``{"request_id": ..., "participant_db_id": ..., "slot_ids": [...]}``
   or ``{"error": "..."}`` on malformed input.

2. ``parse_response`` — parse a natural-language reply (Gmail body or
   Telegram free-text) into structured slot preferences via a single cheap
   Sonnet call. Returns one of:
       - ``{"responses": {slot_id: "yes"|"if_needed"|"no", ...}}``
       - ``{"counter_proposal": "..."}``
       - ``{"error": "..."}``

   Uses ``cosinabox.defaults.SONNET_MODEL_ID`` (never a hardcoded model).
   Records actual spend via ``CostTracker.record(...)`` when a tracker is
   supplied. Malformed JSON falls back to an ``error`` dict, never crashes.

Ported from cos-agent/src/scheduling/response_parser.py, async stripped.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cosinabox.agent.cost import estimate_cost
from cosinabox.defaults import SONNET_MODEL_ID
from cosinabox.scheduling.models import TimeSlot

logger = logging.getLogger(__name__)

_MAX_TOKENS = 300

# Cap reply_text before embedding in the Sonnet prompt. A participant's real
# reply is rarely over a few hundred chars; longer payloads are usually quoted
# email history or adversarial. Cost-of-parse is per-token, per-poll-cycle.
_MAX_REPLY_CHARS = 4000


# ---------------------------------------------------------------------------
# Inline button response parsing (no LLM)
# ---------------------------------------------------------------------------


def parse_callback_data(data: str) -> dict[str, Any]:
    """Parse a Telegram inline-button callback for scheduling.

    Expected format: ``sched_resp:{request_id}:{participant_db_id}:{slot_id}``
    where ``slot_id`` may also be a comma-separated list of ids. Returns a
    dict on success, or ``{"error": "..."}`` on malformed input.
    """
    if not isinstance(data, str) or not data:
        return {"error": "empty callback data"}

    parts = data.split(":")
    if len(parts) != 4:
        return {"error": f"expected 4 colon-separated parts, got {len(parts)}"}
    if parts[0] != "sched_resp":
        return {"error": f"unexpected prefix: {parts[0]!r}"}

    request_id = parts[1]
    if not request_id:
        return {"error": "empty request_id"}

    try:
        participant_db_id = int(parts[2])
        slot_ids = [int(s) for s in parts[3].split(",") if s.strip()]
    except ValueError as exc:
        return {"error": f"non-integer id in callback: {exc}"}

    if not slot_ids:
        return {"error": "no slot ids in callback"}

    return {
        "request_id": request_id,
        "participant_db_id": participant_db_id,
        "slot_ids": slot_ids,
    }


# ---------------------------------------------------------------------------
# Natural-language response parsing (single Sonnet call)
# ---------------------------------------------------------------------------


def _render_slots(
    slots: list[TimeSlot],
    participant_tz: str,
) -> str:
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(participant_tz)
    except Exception:  # pragma: no cover - bad tz defaults to UTC
        tz = ZoneInfo("UTC")

    lines = []
    for i, slot in enumerate(slots, 1):
        local_start = slot.start_time.astimezone(tz)
        local_end = slot.end_time.astimezone(tz)
        day_str = local_start.strftime("%a %d %b")
        time_str = (
            f"{local_start.strftime('%I:%M %p').lstrip('0')} - "
            f"{local_end.strftime('%I:%M %p').lstrip('0')}"
        )
        lines.append(f"Slot {i} (ID {slot.db_id}): {day_str}, {time_str}")
    return "\n".join(lines)


def _extract_json_text(raw: str) -> str:
    """Strip markdown code fences ```json ... ``` if the model added them."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = [ln for ln in lines if not ln.startswith("```")]
        text = "\n".join(json_lines).strip()
    return text


def parse_response(
    *,
    participant_name: str,
    slots: list[TimeSlot],
    reply_text: str,
    anthropic_client: Any,
    cost_tracker: Any | None = None,
    participant_timezone: str = "UTC",
) -> dict[str, Any]:
    """Parse a free-text scheduling reply into structured slot preferences.

    Returns one of::
        {"responses": {"<slot_id>": "yes"|"if_needed"|"no", ...}}
        {"counter_proposal": "<free text>"}
        {"error": "<reason>"}

    Uses a single Sonnet call (cheap — no tool loop). Cost is recorded on
    ``cost_tracker`` if provided. Malformed JSON → ``error`` dict, never
    raises.
    """
    slots_text = _render_slots(slots, participant_timezone)

    if len(reply_text) > _MAX_REPLY_CHARS:
        logger.info(
            "Truncating scheduling reply from %s: %d → %d chars",
            participant_name, len(reply_text), _MAX_REPLY_CHARS,
        )
        reply_text = reply_text[:_MAX_REPLY_CHARS] + "…[truncated]"

    prompt = f"""Parse this scheduling response from {participant_name}.

The participant was asked about these time slots:
{slots_text}

Their response:
"{reply_text}"

Return a JSON object with one of these formats:
1. If they indicated availability for specific slots:
   {{"responses": {{"<slot_id>": "yes"|"if_needed"|"no", ...}}}}
   Include ALL slots — use "yes" for ones they can do, "if_needed" for
   maybes, and "no" for ones they declined or didn't mention.

2. If they proposed an alternative time instead:
   {{"counter_proposal": "description of what they suggested"}}

3. If the response is unclear or unrelated:
   {{"error": "brief description of why it couldn't be parsed"}}

Return ONLY the JSON object, no other text."""

    try:
        response = anthropic_client.messages.create(
            model=SONNET_MODEL_ID,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.error(
            "Scheduling response parsing API call failed: %s", exc, exc_info=True,
        )
        return {"error": f"API call failed: {exc}"}

    # Record spend before parsing — we were billed regardless of JSON validity.
    if cost_tracker is not None:
        try:
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            cache_creation = int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            actual_usd = estimate_cost(
                SONNET_MODEL_ID,
                input_tokens,
                output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
            )
            cost_tracker.record(actual_usd)
        except Exception as exc:  # pragma: no cover - tracker failures are non-fatal
            logger.warning("cost_tracker.record failed: %s", exc)

    try:
        result_text = response.content[0].text
    except (AttributeError, IndexError, TypeError) as exc:
        logger.warning("Unexpected Sonnet response shape: %s", exc)
        return {"error": f"unexpected response shape: {exc}"}

    json_text = _extract_json_text(result_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Sonnet response as JSON: %s", exc)
        return {"error": f"Could not parse LLM response: {exc}"}

    if not isinstance(parsed, dict):
        return {"error": "LLM response was not a JSON object"}
    return parsed
