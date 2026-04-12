"""Pre-meeting prep — fires before upcoming meetings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox import defaults
from cosinabox.jobs.base import Job, JobContext


class PreMeetingPrepJob(Job):
    name = "pre_meeting_prep"

    def __init__(
        self,
        *,
        calendar: Any,
        agent_loop: Any,
        personality: str,
        minutes_before: int = defaults.PRE_MEETING_PREP_MINUTES_BEFORE,
        window_minutes: int = defaults.PRE_MEETING_PREP_WINDOW_MINUTES,
        skip_titles: list[str] | None = None,
    ) -> None:
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.minutes_before = minutes_before
        self.window = window_minutes
        self.skip_titles = [t.lower() for t in (skip_titles or [])]
        self._prepped: set[str] = set()

    def _find_upcoming(self) -> list[Any]:
        """Find events starting within the prep window."""
        now = datetime.now(UTC)
        window_start = now + timedelta(minutes=self.minutes_before - self.window)
        window_end = now + timedelta(minutes=self.minutes_before + self.window)
        events = self.calendar.list_events(start=window_start, end=window_end)
        return [
            e for e in events
            if e.id not in self._prepped
            and window_start <= e.start <= window_end
            and not any(skip in e.summary.lower() for skip in self.skip_titles)
        ]

    def run(self, context: JobContext) -> str:
        upcoming = self._find_upcoming()
        if not upcoming:
            return ""  # Empty = no message sent

        results: list[str] = []
        for event in upcoming:
            self._prepped.add(event.id)
            prompt = (
                f"Prepare a brief for this upcoming meeting:\n"
                f"- Title: {event.summary}\n"
                f"- Time: {event.start.strftime('%H:%M')} - {event.end.strftime('%H:%M')}\n\n"
                "FORMAT: Max 10 lines.\n"
                "1. What this meeting is likely about (based on title)\n"
                "2. Key questions or talking points\n"
                "3. Any prep needed\n\n"
                "Be concise. If the title is self-explanatory, keep it short."
            )
            result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
            if result.final_text:
                time_str = event.start.strftime('%H:%M')
                results.append(
                    f"Meeting: {event.summary} at {time_str}\n{result.final_text}"
                )

        return "\n\n---\n\n".join(results) if results else ""
