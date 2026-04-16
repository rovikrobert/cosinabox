"""Extract durable facts from Fireflies meeting transcripts."""

from __future__ import annotations

import contextlib
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


def _is_stub(transcript: dict[str, Any]) -> bool:
    sentences = transcript.get("sentences") or []
    duration = transcript.get("duration") or 0
    return len(sentences) < 3 or duration < 60


class ExtractFirefliesJob(Job):
    name = "extract_fireflies"

    def __init__(
        self,
        *,
        fireflies: Any | None,
        memory_client: Any,
        db: Any,
        anthropic_client: Any,
        cost_tracker: Any | None = None,
    ) -> None:
        self.fireflies = fireflies
        self.memory_client = memory_client
        self.db = db
        self.anthropic = anthropic_client
        self.cost_tracker = cost_tracker

    def run(self, context: Any = None) -> str:
        if self.fireflies is None:
            return "Fireflies not configured — skipped"

        meetings = self.fireflies.list_recent_meetings(hours=48)
        extracted = 0
        skipped = 0

        for meeting in meetings:
            mid = meeting.get("id", "")
            if not mid or is_source_processed(self.db, "fireflies", mid):
                skipped += 1
                continue

            transcript = self.fireflies.get_transcript(mid)
            if _is_stub(transcript):
                mark_source_processed(self.db, "fireflies", mid)
                skipped += 1
                continue

            sentences = transcript.get("sentences") or []
            content = f"Meeting: {meeting.get('title', 'Untitled')}\n\n"
            content += "\n".join(
                f"{s.get('speaker_name', 'Unknown')}: {s.get('text', '')}" for s in sentences[:100]
            )
            if len(content) > 5000:
                content = content[:5000] + "... (truncated)"

            try:
                response = self.anthropic.messages.create(
                    model=SONNET_MODEL_ID,
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": EXTRACTION_PROMPT.format(content=content),
                        }
                    ],
                )
                resp_text = "\n".join(b.text for b in response.content if b.type == "text")
                # Track cost
                if self.cost_tracker is not None:
                    from cosinabox.agent.cost import estimate_cost

                    with contextlib.suppress(Exception):
                        self.cost_tracker.record(
                            estimate_cost(
                                SONNET_MODEL_ID,
                                response.usage.input_tokens,
                                response.usage.output_tokens,
                            )
                        )
                facts = parse_extraction_response(resp_text)
            except Exception:
                logger.warning("Extraction failed for transcript %s", mid, exc_info=True)
                continue

            # Mark-on-success only: same reasoning as extract_gmail.py.
            # Partial-failure means re-run may duplicate facts, but that's
            # strictly better than losing data + marking processed.
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
                        "Memory store failed for fireflies source %s — "
                        "will retry on next run (duplicates possible)",
                        mid,
                        exc_info=True,
                    )
                    store_failed = True
                    break

            if not store_failed:
                mark_source_processed(self.db, "fireflies", mid)

        return f"Fireflies: {extracted} facts from {len(meetings)} transcripts ({skipped} skipped)"
