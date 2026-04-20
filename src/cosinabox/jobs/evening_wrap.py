"""Evening wrap — today's shipped work + commitment-grounded carry-over.

Prefetch:
- ``SENT MAIL TODAY`` — DONE section draws from here.
- ``COMMITMENT VERIFICATION`` — if a ``Memory`` instance is wired in and
  the open-commitments list is non-empty, every open commitment is
  auto-checked against sent mail. CARRY-OVER / TOMORROW are only produced
  when ``GENUINELY OPEN`` items exist. Without a db, the wrap falls back
  to the 2026-04-18 sent-mail-only mode (no carry-over).
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
        db: Any | None = None,
    ) -> None:
        self.gmail = gmail
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.db = db

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

        # Commitment verification (only when a db is wired in).
        if self.db is not None:
            try:
                from cosinabox.commitments.auto_resolve import (
                    format_for_briefing,
                    verify_all_open_commitments,
                )

                verified = verify_all_open_commitments(self.db, self.gmail)
                formatted = format_for_briefing(verified)
                if formatted:
                    sections.append(formatted)
            except Exception:
                # Never let verification failure break the wrap. The
                # absolute prompt rule below still forbids fabrication.
                pass

        return "\n\n".join(sections)

    def run(self, context: JobContext) -> str:
        prefetched = self._prefetch()
        today = datetime.now(UTC).strftime("%A, %B %d, %Y")

        has_commitments = self.db is not None

        if has_commitments:
            prompt = (
                f"End-of-day wrap for {self.name_for_briefing}, TODAY: {today}.\n\n"
                "FORMAT: Max 12 lines.\n"
                "1. DONE — what actually got completed today, from SENT MAIL.\n"
                "2. CARRY-OVER — items from GENUINELY OPEN only. Nothing else.\n"
                "3. TOMORROW — top 3 from GENUINELY OPEN for first thing.\n\n"
                "ABSOLUTE RULES (zero exceptions):\n"
                "- If COMMITMENT VERIFICATION shows VERIFIED DONE → it IS done.\n"
                "  NEVER list as carry-over.\n"
                "- If COMMITMENT VERIFICATION shows LIKELY DONE → treat as done.\n"
                "  Only flag if the user might disagree.\n"
                "- Only items in GENUINELY OPEN can be carry-overs or tomorrow.\n"
                "- Do not invent items. Do not infer from memory or prior briefings.\n"
                "- If sent mail shows an email was sent, it IS done — don't hedge.\n"
                "- If GENUINELY OPEN is empty, skip CARRY-OVER + TOMORROW entirely.\n\n"
                f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
            )
        else:
            # No commitments DB wired in — stay in the PR #56 sent-mail-only
            # mode. Keeps older deployments honest rather than fabricating.
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
