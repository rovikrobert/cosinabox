"""Morning briefing job: calendar + email + follow-ups, persona-styled.

Layer 1: graceful degradation — any missing tool means the section is
skipped, not a crash.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.prompts.briefing import render_briefing_prompt


class MorningBriefingJob(Job):
    name = "morning_briefing"

    def __init__(
        self,
        *,
        gmail: Any | None,
        calendar: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str = "user",
        followups: str = "(none)",
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.followups = followups

    def run(self, context: JobContext) -> str:
        now = datetime.now(UTC)
        end = now + timedelta(hours=12)

        cal_summary = "(calendar not configured)"
        if self.calendar is not None:
            events = self.calendar.list_events(start=now, end=end)
            cal_summary = "\n".join(
                f"- {e.summary}" for e in events
            ) or "(no events today)"

        email_summary = "(email not configured)"
        if self.gmail is not None:
            msgs = self.gmail.list_recent(hours=24, max_results=15)
            email_summary = "\n".join(
                f"- {m.sender}: {m.subject}" for m in msgs
            ) or "(no recent email)"

        prompt = render_briefing_prompt(
            personality=self.personality,
            name=self.name_for_briefing,
            calendar_summary=cal_summary,
            email_summary=email_summary,
            followups=self.followups,
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return str(result.final_text)
