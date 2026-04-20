"""Weekly review — week recap with relationship health."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class WeeklyReviewJob(Job):
    name = "weekly_review"

    def __init__(
        self,
        *,
        gmail: Any,
        calendar: Any,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
        stakeholders: list[dict[str, Any]] | None = None,
        db: Any | None = None,
        drive: Any | None = None,
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.stakeholders = stakeholders or []
        self.db = db
        self.drive = drive

    def _prefetch(self) -> str:
        sections: list[str] = []
        now = datetime.now(UTC)
        week_start = now - timedelta(days=7)

        # Calendar — full week
        try:
            events = self.calendar.list_events(start=week_start, end=now)
            if events:
                lines = [f"- {e.start.strftime('%a %H:%M')} {e.summary}" for e in events]
                header = f"CALENDAR (past 7 days, {len(events)} events):"
                sections.append(header + "\n" + "\n".join(lines))
            else:
                sections.append("CALENDAR:\n(no events this week)")
        except Exception:
            sections.append("CALENDAR:\n(unavailable)")

        # Sent mail — full week
        try:
            sent = self.gmail.search("in:sent newer_than:7d", max_results=25)
            if sent:
                lines = [f"- To: {e.sender} | Subject: {e.subject}" for e in sent]
                sections.append(f"SENT MAIL THIS WEEK ({len(sent)} messages):\n" + "\n".join(lines))
            else:
                sections.append("SENT MAIL:\n(none)")
        except Exception:
            sections.append("SENT MAIL:\n(unavailable)")

        # Stakeholder health
        if self.stakeholders:
            lines = []
            for s in self.stakeholders:
                sh_name = s.get("name", "?")
                role = s.get("role", "")
                cadence = s.get("cadence", "?")
                lc = s.get("last_contact") or s.get("last_interaction") or "unknown"
                lines.append(f"- {sh_name} ({role}) — cadence: {cadence}, last: {lc}")
            sections.append("STAKEHOLDER HEALTH:\n" + "\n".join(lines))

        # Commitment verification when a db is wired in. Grounds MISSES /
        # NEXT WEEK in GENUINELY OPEN vs dropping them entirely.
        if self.db is not None:
            try:
                from cosinabox.commitments.auto_resolve import (
                    format_for_briefing,
                    verify_all_open_commitments,
                )

                verified = verify_all_open_commitments(self.db, self.gmail, drive=self.drive)
                formatted = format_for_briefing(verified)
                if formatted:
                    sections.append(formatted)
            except Exception:
                pass

        return "\n\n".join(sections)

    def run(self, context: JobContext) -> str:
        prefetched = self._prefetch()
        today = datetime.now(UTC).strftime("%A, %B %d, %Y")

        has_commitments = self.db is not None

        if has_commitments:
            prompt = (
                f"Weekly review for {self.name_for_briefing}, week ending {today}.\n\n"
                "FORMAT: Max 25 lines.\n"
                "1. WINS — what shipped this week from SENT MAIL + CALENDAR.\n"
                "2. MISSES — items in GENUINELY OPEN that were due this week\n"
                "   (deadline past) or carry priority 1–2. Nothing else.\n"
                "3. RELATIONSHIP HEALTH — use STAKEHOLDER HEALTH.\n"
                "4. NEXT WEEK — top 3 from GENUINELY OPEN ordered by\n"
                "   (deadline, priority).\n\n"
                "ABSOLUTE RULES (zero exceptions):\n"
                "- If COMMITMENT VERIFICATION shows VERIFIED DONE → NEVER list\n"
                "  as a miss or next-week item.\n"
                "- If LIKELY DONE → treat as done.\n"
                "- Only items in GENUINELY OPEN can appear in MISSES or NEXT WEEK.\n"
                "- Do not invent items. Do not infer from memory.\n"
                "- If GENUINELY OPEN is empty, skip MISSES + NEXT WEEK entirely.\n"
                "- Be direct. This is a forcing function, not a pat on the back.\n\n"
                f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
            )
        else:
            # No db: PR #56 behavior — drop MISSES + NEXT WEEK sections.
            prompt = (
                f"Weekly review for {self.name_for_briefing}, week ending {today}.\n\n"
                "FORMAT: Max 20 lines.\n"
                "1. WINS — what actually shipped or moved forward this week, drawn\n"
                "   from SENT MAIL + CALENDAR events only.\n"
                "2. RELATIONSHIP HEALTH — use STAKEHOLDER HEALTH to flag anyone\n"
                "   whose cadence has slipped or is newly active.\n\n"
                "ABSOLUTE RULES:\n"
                "- ONLY surface items present in the pre-fetched data.\n"
                "- Do not invent items. Do not infer from memory or prior reviews.\n"
                "- Do NOT generate MISSES or NEXT WEEK sections. This build has no\n"
                "  grounded source for open commitments or 'what was planned';\n"
                "  anything there would be fabricated. (Once the commitments +\n"
                "  auto_resolve subsystem ports from cos-agent, re-enable those\n"
                "  sections with a verified-done vs genuinely-open ground truth.)\n"
                "- Be direct. This is a forcing function, not a pat on the back.\n\n"
                f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
            )

        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text or "(no review generated)"
