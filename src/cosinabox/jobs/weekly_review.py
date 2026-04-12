"""Weekly review job: 7-day calendar + sent mail + relationships recap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class WeeklyReviewJob(Job):
    name = "weekly_review"

    def __init__(
        self,
        *,
        gmail: Any | None,
        calendar: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing

    def run(self, context: JobContext) -> str:
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)
        cal_summary = "(no calendar)"
        if self.calendar is not None:
            events = self.calendar.list_events(start=week_ago, end=now)
            cal_summary = "\n".join(f"- {e.summary}" for e in events) or "(empty week)"
        sent_summary = "(no email)"
        if self.gmail is not None:
            sent = self.gmail.search("from:me newer_than:7d", max_results=50)
            sent_summary = "\n".join(f"- {m.subject}" for m in sent) or "(no sent mail)"
        prompt = (
            f"Personality:\n{self.personality}\n\n"
            f"Compose {self.name_for_briefing}'s weekly review.\n\n"
            f"## Calendar last 7 days\n{cal_summary}\n\n"
            f"## Sent mail last 7 days\n{sent_summary}\n\n"
            f"Surface: themes, missed connections, who didn't get a reply."
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return str(result.final_text)
