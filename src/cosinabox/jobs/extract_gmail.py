"""Extract durable facts from stakeholder emails."""

from __future__ import annotations

import logging
from typing import Any

from cosinabox.agent.routing import SONNET_MODEL_ID
from cosinabox.jobs.base import Job
from cosinabox.jobs.extraction import (
    EXTRACTION_PROMPT,
    is_source_processed,
    mark_source_processed,
    parse_extraction_response,
)
from cosinabox.memory.client import MemoryServiceError

logger = logging.getLogger(__name__)

_ACTIVE_CADENCES = {"daily", "weekly"}


def build_stakeholder_query(stakeholders: list[dict[str, Any]]) -> str:
    emails = [
        s["email"]
        for s in stakeholders
        if s.get("email") and s.get("cadence", "").lower() in _ACTIVE_CADENCES
    ]
    if not emails:
        return ""
    return " OR ".join(f"from:{e}" for e in emails)


class ExtractGmailJob(Job):
    name = "extract_gmail"

    def __init__(
        self,
        *,
        gmail: Any | None,
        memory_client: Any,
        db: Any,
        anthropic_client: Any,
        stakeholders: list[dict[str, Any]],
        cost_tracker: Any | None = None,
    ) -> None:
        self.gmail = gmail
        self.memory_client = memory_client
        self.db = db
        self.anthropic = anthropic_client
        self.stakeholders = stakeholders
        self.cost_tracker = cost_tracker

    def run(self, context: Any = None) -> str:
        if self.gmail is None:
            return "Gmail not configured — skipped"

        query = build_stakeholder_query(self.stakeholders)
        if not query:
            return "No stakeholders with daily/weekly cadence and email — 0 facts"

        messages = self.gmail.search(query, max_results=50)
        extracted = 0
        skipped = 0

        for msg in messages:
            if is_source_processed(self.db, "gmail", msg.id):
                skipped += 1
                continue

            content = f"From: {msg.sender}\nSubject: {msg.subject}\n\n{msg.snippet}"

            try:
                response = self.anthropic.messages.create(
                    model=SONNET_MODEL_ID,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(content=content)}],
                )
                resp_text = "\n".join(b.text for b in response.content if b.type == "text")
                # Track cost
                if self.cost_tracker is not None:
                    from cosinabox.agent.cost import estimate_cost
                    try:
                        self.cost_tracker.record(estimate_cost(
                            SONNET_MODEL_ID,
                            response.usage.input_tokens,
                            response.usage.output_tokens,
                        ))
                    except Exception:
                        pass
                facts = parse_extraction_response(resp_text)
            except Exception:
                logger.warning("Extraction failed for email %s", msg.id, exc_info=True)
                continue

            # Mark-on-success only: if any store() raises we do NOT mark
            # the source processed. On re-run, the already-stored facts may
            # duplicate — that's better than silent data loss + source
            # marked done. See memory/client.py: MemoryServiceError.
            store_failed = False
            for fact in facts:
                try:
                    self.memory_client.store(
                        text=fact.get("text", ""),
                        metadata=fact.get("metadata", {}),
                        namespace="extraction",
                    )
                    extracted += 1
                except MemoryServiceError:
                    logger.warning(
                        "Memory store failed for gmail source %s — "
                        "will retry on next run (duplicates possible)",
                        msg.id,
                        exc_info=True,
                    )
                    store_failed = True
                    break

            if not store_failed:
                mark_source_processed(self.db, "gmail", msg.id)

        return f"Gmail: {extracted} facts from {len(messages)} emails ({skipped} skipped)"
