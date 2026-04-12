"""Pre-meeting prep job: fires for events 25-35 min out by default.

Layer 1: pre-meeting prep needs a window. Filtering matters.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class PreMeetingPrepJob(Job):
    name = "pre_meeting_prep"

    def __init__(
        self,
        *,
        calendar: Any,
        agent_loop: Any,
        personality: str,
        minutes_before: int = 30,
        window_minutes: int = 5,
        skip_titles: list[str] | None = None,
    ) -> None:
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.minutes_before = minutes_before
        self.window_minutes = window_minutes
        self.skip_titles = [t.lower() for t in (skip_titles or [])]

    def run(self, context: JobContext) -> str:
        if self.calendar is None:
            return "(calendar not configured — pre_meeting_prep is a no-op)"
        now = datetime.now(UTC)
        win_start = now + timedelta(minutes=self.minutes_before - self.window_minutes)
        win_end = now + timedelta(minutes=self.minutes_before + self.window_minutes)
        candidates = self.calendar.list_events(start=win_start, end=win_end)
        outputs: list[str] = []
        for evt in candidates:
            # Secondary filter: ensure event start is within window
            # (handles mocks or calendars that don't filter by window)
            evt_start = evt.start
            if isinstance(evt_start, datetime) and not (win_start <= evt_start <= win_end):
                continue
            title = (evt.summary or "").lower()
            if any(skip in title for skip in self.skip_titles):
                continue
            prompt = (
                f"Personality:\n{self.personality}\n\n"
                f"Pre-meeting prep for: {evt.summary}\n"
                f"Starts: {evt.start}\n"
                f"Write a 3-line brief: who's in the meeting, recent context, "
                f"one question to ask."
            )
            result = self.agent_loop.run(prompt=prompt, session_id=f"{context.session_id}-{evt.id}")
            outputs.append(f"[{evt.summary}] {result.final_text}")
        return "\n".join(outputs) or "(no upcoming meetings in window)"
