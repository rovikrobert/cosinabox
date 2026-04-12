"""Evening wrap job: sent mail recap + open commitments."""

from __future__ import annotations

from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.prompts.briefing import render_briefing_prompt


class EveningWrapJob(Job):
    name = "evening_wrap"

    def __init__(
        self,
        *,
        gmail: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
    ) -> None:
        self.gmail = gmail
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing

    def run(self, context: JobContext) -> str:
        sent_summary = "(email not configured)"
        if self.gmail is not None:
            sent = self.gmail.search("from:me newer_than:12h", max_results=20)
            sent_summary = (
                "\n".join(f"- {m.subject}" for m in sent) or "(no sent mail in last 12 hours)"
            )
        prompt = render_briefing_prompt(
            personality=self.personality,
            name=self.name_for_briefing,
            calendar_summary="(end of day)",
            email_summary=f"Sent today:\n{sent_summary}",
            followups="(commitments tracking deferred to v0.2)",
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return str(result.final_text)
