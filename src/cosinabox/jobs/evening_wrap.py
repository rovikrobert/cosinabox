"""Evening wrap — what got done today, what carries over."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class EveningWrapJob(Job):
    name = "evening_wrap"

    def __init__(
        self,
        *,
        gmail: Any,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
    ) -> None:
        self.gmail = gmail
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing

    def _prefetch(self) -> str:
        sections: list[str] = []

        # Sent mail today
        try:
            sent = self.gmail.search("in:sent newer_than:12h", max_results=15)
            if sent:
                lines = [f"- To: {e.sender} | Subject: {e.subject}" for e in sent]
                sections.append("SENT MAIL TODAY:\n" + "\n".join(lines))
            else:
                sections.append("SENT MAIL TODAY:\n(none)")
        except Exception:
            sections.append("SENT MAIL TODAY:\n(unavailable)")

        return "\n\n".join(sections)

    def run(self, context: JobContext) -> str:
        prefetched = self._prefetch()
        today = datetime.now(UTC).strftime("%A, %B %d, %Y")

        prompt = (
            f"End-of-day wrap for {self.name_for_briefing}, TODAY: {today}.\n\n"
            "FORMAT: Max 12 lines total.\n"
            "1. DONE — what actually got completed today (based on sent mail). Facts only.\n"
            "2. CARRY-OVER — anything urgent that didn't get done.\n"
            "3. TOMORROW — anything urgent for first thing.\n\n"
            "RULES:\n"
            "- If sent mail shows an email was sent, it IS done.\n"
            "- Don't dress up a slow day. If nothing meaningful moved, say so.\n"
            "- Be honest about carry-overs.\n\n"
            f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
        )

        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text or "(no wrap generated)"
