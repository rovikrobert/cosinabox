"""Telegram inline-button callback handler for scheduling polls.

When a participant taps a slot button on a scheduling poll DM, the
callback_data is ``sched_resp:{request_id}:{participant_db_id}:{slot_id}``
(slot_id may be a comma-separated list for multi-select). This handler:

1. Parses the callback via ``response_parser.parse_callback_data``.
2. Records a "yes" response for each selected slot in the DB.
3. Answers the callback with a confirmation toast (or an error alert if
   the callback data is malformed).

The handler is wired into ``TelegramBot`` via ``register_callback_handler``
(see ``app.py`` / Task 11). This module only exposes the builder.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.response_parser import parse_callback_data

logger = logging.getLogger(__name__)


def build_scheduling_callback_handler(db: Any) -> Callable:
    """Return an async handler ``(update, ctx) -> None`` bound to ``db``."""

    async def handle_scheduling_callback(update: Any, _ctx: Any) -> None:
        query = update.callback_query
        data = getattr(query, "data", None) or ""

        parsed = parse_callback_data(data)
        if "error" in parsed:
            logger.warning(
                "Malformed scheduling callback data %r: %s",
                data, parsed["error"],
            )
            await query.answer("Invalid response format", show_alert=True)
            return

        request_id = parsed["request_id"]
        participant_db_id = parsed["participant_db_id"]
        slot_ids = parsed["slot_ids"]

        try:
            for slot_id in slot_ids:
                sched_db.record_response(
                    db,
                    request_id=request_id,
                    participant_db_id=participant_db_id,
                    slot_db_id=slot_id,
                    response="yes",
                )
        except Exception as exc:
            logger.exception(
                "Failed to record scheduling response for request=%s participant=%s: %s",
                request_id, participant_db_id, exc,
            )
            await query.answer("Error recording response", show_alert=True)
            return

        await query.answer("Thanks — response recorded", show_alert=False)
        logger.info(
            "Scheduling response recorded via callback: request=%s participant=%s slots=%s",
            request_id, participant_db_id, slot_ids,
        )

    return handle_scheduling_callback
