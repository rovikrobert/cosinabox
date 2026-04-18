"""Evening wrap — what actually shipped today, based only on sent mail.

CARRY-OVER and TOMORROW sections were removed 2026-04-18: with only sent
mail in the prefetch, those sections confabulated items from conversation
memory / speculative tool calls (observed zombie items: "Recruiter
shortlist", "SOW with Daniel" still-open days after resolution). cos-agent
grounds them via `auto_resolve.verify_all_open_commitments`, which requires
a commitments DB that cosinabox hasn't ported yet. Until then, the evening
wrap stays honest about what it can prove: sent mail.
"""

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
            "FORMAT: Max 8 lines.\n"
            "DONE — what actually got completed today, one line per item.\n\n"
            "ABSOLUTE RULES:\n"
            "- ONLY use items from the pre-fetched SENT MAIL section.\n"
            "- Do not invent items. Do not infer from memory or prior briefings.\n"
            "- If sent mail shows an email was sent, it IS done — don't hedge.\n"
            "- If sent mail is empty or thin, say 'Quiet day — nothing major shipped.'\n"
            "  and stop. Do NOT generate a CARRY-OVER or TOMORROW section.\n"
            "- Do NOT produce CARRY-OVER or TOMORROW sections. This build has\n"
            "  no grounded source for open commitments; anything there would be\n"
            "  fabricated.\n\n"
            f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
        )

        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text or "(no wrap generated)"
