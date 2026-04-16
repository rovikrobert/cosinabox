"""Multi-channel outreach for group scheduling (sync).

Sends scheduling polls via Telegram DM (inline keyboard) or Gmail draft.
Gmail outreach is ALWAYS a draft first — the owner reviews before sending.

This module is a sync port of cos-agent/src/scheduling/outreach.py, generalised:
- Hardcoded "Rovik"/"SGT" replaced with owner_name + owner_timezone params.
- async → sync. `bot` and `gmail` are duck-typed adapters injected by the caller.

Bot adapter contract (sync):
    bot.send_poll(
        *, chat_id: str | int, text: str,
        buttons: list[tuple[str, str]],  # (label, callback_data) one per row
    ) -> dict  # must contain "message_id"

Gmail adapter contract (sync) — matches cosinabox.tools.google.gmail.GmailTool:
    gmail.compose_draft(*, to: str, subject: str, body: str) -> dict  # contains "draft_id"
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import Participant, SchedulingRequest, TimeSlot

logger = logging.getLogger(__name__)


def _tz_label(tz_name: str, at: datetime | None = None) -> str:
    """Return a short TZ label (e.g. 'SGT', 'PST'). Falls back to the city suffix."""
    try:
        moment = at or datetime.now(ZoneInfo(tz_name))
        label = moment.tzname()
        if label:
            return label
    except Exception:
        pass
    # Fallback: use the city segment of an IANA zone
    return tz_name.split("/")[-1] if "/" in tz_name else tz_name


def _format_slot_lines(
    slots: list[TimeSlot], participant_tz: str, *, long_form: bool,
) -> list[str]:
    """Render slot list localized to participant tz. Long form for email, short for chat."""
    p_tz = ZoneInfo(participant_tz)
    lines: list[str] = []
    for i, slot in enumerate(slots, 1):
        local_start = slot.start_time.astimezone(p_tz)
        local_end = slot.end_time.astimezone(p_tz)
        if long_form:
            day_str = local_start.strftime("%A, %d %B")
        else:
            day_str = local_start.strftime("%a %d %b")
        time_str = (
            f"{local_start.strftime('%I:%M %p').lstrip('0')} - "
            f"{local_end.strftime('%I:%M %p').lstrip('0')}"
        )
        tz_label = _tz_label(participant_tz, local_start)
        prefix = "  " if long_form else ""
        lines.append(f"{prefix}{i}. {day_str}, {time_str} {tz_label}")
    return lines


# ---------------------------------------------------------------------------
# Telegram outreach (sync)
# ---------------------------------------------------------------------------


def send_telegram_poll(
    *,
    bot: Any,
    participant: Participant,
    request: SchedulingRequest,
    slots: list[TimeSlot],
    owner_timezone: str,
    db: Any | None = None,
    owner_name: str = "your host",
) -> dict[str, Any]:
    """Send a scheduling poll via Telegram DM with inline keyboard buttons.

    Each button has callback_data of the form
        `sched_resp:{req_id}:{participant_db_id}:{slot_db_id}`

    Returns:
        {"status": "sent", "channel": "telegram", "message_id": ..., ...}
        or {"status": "error", "reason": ...}
    """
    if not participant.telegram_id:
        return {
            "status": "error",
            "channel": "telegram",
            "participant": participant.name,
            "reason": "no telegram_id",
        }
    if participant.db_id is None:
        return {
            "status": "error",
            "channel": "telegram",
            "participant": participant.name,
            "reason": "participant has no db_id",
        }

    # Build message text
    other_names = [p.name for p in request.participants if p.name != participant.name]
    others_str = ", ".join(other_names) if other_names else "others"

    first_name = participant.name.split()[0] if participant.name else "there"
    lines = [
        f"Hey {first_name}, {owner_name} is looking to schedule a "
        f"{request.duration_minutes}-min {request.title} with {others_str}. "
        f"Would any of these work for you?",
        "",
    ]
    lines.extend(_format_slot_lines(slots, participant.timezone, long_form=False))
    lines.append("")
    lines.append(
        "Tap the buttons below to select which times work, "
        "or reply with alternatives."
    )
    text = "\n".join(lines)

    # Build buttons: one per slot with callback_data
    p_tz = ZoneInfo(participant.timezone)
    buttons: list[tuple[str, str]] = []
    for i, slot in enumerate(slots, 1):
        if slot.db_id is None:
            continue
        local_start = slot.start_time.astimezone(p_tz)
        label = f"{i}. {local_start.strftime('%a %d %b %I:%M%p').lstrip('0')}"
        callback_data = (
            f"sched_resp:{request.id}:{participant.db_id}:{slot.db_id}"
        )
        buttons.append((label, callback_data))

    try:
        result = bot.send_poll(
            chat_id=participant.telegram_id,
            text=text,
            buttons=buttons,
        )
        message_id = result.get("message_id") if isinstance(result, dict) else None

        if db is not None:
            try:
                sched_db.update_participant_status(
                    db, participant.db_id, "sent", mark_outreach_sent=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to update participant status: %s", exc)

        return {
            "status": "sent",
            "channel": "telegram",
            "participant": participant.name,
            "message_id": message_id,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to send Telegram poll to %s (%s): %s",
            participant.name, participant.telegram_id, exc,
        )
        return {
            "status": "error",
            "channel": "telegram",
            "participant": participant.name,
            "reason": str(exc),
        }


# ---------------------------------------------------------------------------
# Gmail outreach (draft only)
# ---------------------------------------------------------------------------


def send_gmail_draft(
    *,
    gmail: Any,
    participant: Participant,
    request: SchedulingRequest,
    slots: list[TimeSlot],
    owner_name: str,
    owner_timezone: str,
    db: Any | None = None,
) -> dict[str, Any]:
    """Create a Gmail draft for scheduling outreach (never auto-sent)."""
    if not participant.email:
        return {
            "status": "error",
            "channel": "gmail",
            "participant": participant.name,
            "reason": "no email",
        }

    tz_label_short = _tz_label(participant.timezone)

    other_names = [p.name for p in request.participants if p.name != participant.name]
    others_str = ", ".join(other_names) if other_names else "the team"

    slot_lines = _format_slot_lines(slots, participant.timezone, long_form=True)

    first_name = participant.name.split()[0] if participant.name else "there"
    body = (
        f"Hi {first_name},\n\n"
        f"I'm writing on behalf of {owner_name} to find a time for a "
        f"{request.duration_minutes}-minute {request.title} with {others_str}.\n\n"
        f"Would any of the following work for you? "
        f"(times shown in {tz_label_short}):\n\n"
        + "\n".join(slot_lines)
        + "\n\n"
        f"If none work, please suggest alternatives and I'll coordinate.\n\n"
        f"Best regards,\n"
        f"{owner_name}'s scheduling assistant"
    )
    subject = f"Scheduling: {request.title} — availability check"

    try:
        result = gmail.compose_draft(
            to=participant.email, subject=subject, body=body,
        )
        draft_id = result.get("draft_id") if isinstance(result, dict) else None
        thread_id = result.get("thread_id") if isinstance(result, dict) else None

        # Draft is created but NOT sent; leave status as 'pending' but record draft_id.
        if db is not None and participant.db_id is not None:
            try:
                sched_db.update_participant_status(
                    db, participant.db_id, "pending",
                    gmail_draft_id=draft_id,
                    gmail_thread_id=thread_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to record draft_id for participant: %s", exc)

        return {
            "status": "draft_created",
            "channel": "gmail",
            "participant": participant.name,
            "draft_id": draft_id,
            "thread_id": thread_id,
            "note": f"Draft created — {owner_name} must review and approve sending.",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to create Gmail draft for %s (%s): %s",
            participant.name, participant.email, exc,
        )
        return {
            "status": "error",
            "channel": "gmail",
            "participant": participant.name,
            "reason": str(exc),
        }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def execute_outreach(
    *,
    request: SchedulingRequest,
    slots: list[TimeSlot],
    bot: Any | None,
    gmail: Any | None,
    owner_name: str,
    owner_timezone: str,
    db: Any | None = None,
) -> str:
    """Dispatch outreach to each participant by channel and update DB status.

    Returns a human-readable summary for the owner.
    """
    if not request.participants:
        return "Outreach error: no participants on this request."

    telegram_sent: list[str] = []
    gmail_drafts: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    any_handled = False

    for participant in request.participants:
        channel = participant.channel
        if channel == "telegram":
            if bot is None:
                status = {
                    "status": "skipped: no_telegram",
                    "participant": participant.name,
                    "reason": "no telegram bot configured",
                }
                if db is not None and participant.db_id is not None:
                    with contextlib.suppress(Exception):
                        sched_db.update_participant_status(
                            db, participant.db_id, "skipped: no_telegram",
                        )
                skipped.append(
                    f"{participant.name} (telegram — no bot configured)"
                )
            else:
                any_handled = True
                status = send_telegram_poll(
                    bot=bot,
                    participant=participant,
                    request=request,
                    slots=slots,
                    owner_timezone=owner_timezone,
                    owner_name=owner_name,
                    db=db,
                )
                if status.get("status") == "sent":
                    telegram_sent.append(participant.name)
                else:
                    errors.append(
                        f"{participant.name} (telegram): {status.get('reason', 'unknown')}"
                    )

        elif channel == "gmail":
            if gmail is None:
                if db is not None and participant.db_id is not None:
                    with contextlib.suppress(Exception):
                        sched_db.update_participant_status(
                            db, participant.db_id, "skipped: no_gmail",
                        )
                skipped.append(
                    f"{participant.name} (gmail — no gmail configured)"
                )
            else:
                any_handled = True
                status = send_gmail_draft(
                    gmail=gmail,
                    participant=participant,
                    request=request,
                    slots=slots,
                    owner_name=owner_name,
                    owner_timezone=owner_timezone,
                    db=db,
                )
                if status.get("status") == "draft_created":
                    gmail_drafts.append(participant.name)
                else:
                    errors.append(
                        f"{participant.name} (gmail): {status.get('reason', 'unknown')}"
                    )
        else:
            skipped.append(f"{participant.name} (unknown channel: {channel})")

    if not any_handled and not telegram_sent and not gmail_drafts:
        return (
            "Outreach error: no reachable participants "
            "(no telegram bot and/or no gmail adapter configured, "
            "or all participants lack a channel)."
        )

    lines: list[str] = [f"Outreach summary for '{request.title}':"]
    if telegram_sent:
        lines.append(
            f"  Telegram sent ({len(telegram_sent)}): "
            + ", ".join(telegram_sent)
        )
    if gmail_drafts:
        lines.append(
            f"  Gmail drafts created ({len(gmail_drafts)}) "
            f"— review in Gmail before sending: "
            + ", ".join(gmail_drafts)
        )
    if skipped:
        lines.append(f"  Skipped ({len(skipped)}): " + "; ".join(skipped))
    if errors:
        lines.append(f"  Errors ({len(errors)}): " + "; ".join(errors))
    return "\n".join(lines)
