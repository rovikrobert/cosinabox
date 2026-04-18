"""Morning briefing — pre-fetch then generate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class MorningBriefingJob(Job):
    name = "morning_briefing"

    def __init__(
        self,
        *,
        gmail: Any,
        calendar: Any,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
        stakeholders: list[dict[str, Any]] | None = None,
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.stakeholders = stakeholders or []

    def _prefetch(self) -> str:
        """Pre-fetch all data sources and assemble into a single block."""
        sections: list[str] = []
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0)
        today_end = today_start + timedelta(days=1)

        # Calendar
        try:
            events = self.calendar.list_events(start=today_start, end=today_end)
            if events:
                lines = [
                    f"- {e.summary} ({e.start.strftime('%H:%M')}-{e.end.strftime('%H:%M')})"
                    for e in events
                ]
                sections.append("CALENDAR:\n" + "\n".join(lines))
            else:
                sections.append("CALENDAR:\n(no events today)")
        except Exception:
            sections.append("CALENDAR:\n(unavailable)")

        # Email — recent
        try:
            emails = self.gmail.list_recent(hours=12, max_results=15)
            if emails:
                lines = [f"- From: {e.sender} | Subject: {e.subject}" for e in emails]
                sections.append("RECENT EMAIL (last 12h):\n" + "\n".join(lines))
            else:
                sections.append("RECENT EMAIL:\n(none)")
        except Exception:
            sections.append("RECENT EMAIL:\n(unavailable)")

        # Email — threads where the LAST message isn't from the user.
        # `is:unread` is a bad proxy: it catches things you opened on mobile
        # and things you already replied to on another device. `threads.list`
        # + SENT-label check on the last message is deterministic.
        try:
            needs_reply = self.gmail.list_threads_needing_reply(hours=24, max_results=10)
            if needs_reply:
                lines = [
                    f"- From: {t.last_sender} | Subject: {t.subject}"
                    + (f" | Snippet: {t.last_snippet[:120]}" if t.last_snippet else "")
                    for t in needs_reply
                ]
                sections.append("INBOX NEEDING REPLY (24h):\n" + "\n".join(lines))
        except AttributeError:
            # Older GmailTool without list_threads_needing_reply — fall back
            # to the old unread search so existing deployments stay working
            # until they upgrade. Remove once the grace window lapses.
            try:
                unreplied = self.gmail.search("is:unread newer_than:24h", max_results=10)
                if unreplied:
                    lines = [f"- From: {e.sender} | Subject: {e.subject}" for e in unreplied]
                    sections.append("UNREAD EMAIL (24h):\n" + "\n".join(lines))
            except Exception:
                pass
        except Exception:
            pass

        # Stakeholder pulse
        if self.stakeholders:
            stale = []
            for s in self.stakeholders:
                lc = s.get("last_contact") or s.get("last_interaction")
                if lc:
                    try:
                        from datetime import date

                        days_ago = (date.today() - date.fromisoformat(str(lc)[:10])).days
                        cadence = s.get("cadence", "weekly")
                        cadence_days = {
                            "daily": 1,
                            "weekly": 7,
                            "biweekly": 14,
                            "monthly": 30,
                            "quarterly": 90,
                        }
                        threshold = cadence_days.get(cadence, 7)
                        if days_ago > threshold:
                            stale.append(
                                f"- {s.get('name', '?')} ({s.get('role', '')}) "
                                f"— {days_ago}d since last contact, cadence: {cadence}"
                            )
                    except (ValueError, TypeError):
                        pass
            if stale:
                sections.append("COOLING CONTACTS:\n" + "\n".join(stale))

        return "\n\n".join(sections)

    def run(self, context: JobContext) -> str:
        prefetched = self._prefetch()
        today = datetime.now(UTC).strftime("%A, %B %d, %Y")

        prompt = (
            f"Generate {self.name_for_briefing}'s morning briefing for TODAY: {today}.\n\n"
            "FORMAT: Max 25 lines. One line per item. Skip empty sections.\n"
            "1. SCHEDULE — meetings with times. Flag any needing prep.\n"
            "2. EMAIL — items where the ball is in the user's court.\n"
            "   Only surface threads from INBOX NEEDING REPLY. For each, lead with\n"
            "   the pending ask; don't recommend actions the user already took.\n"
            "3. PRIORITIES — top 3 based on calendar + email signals.\n"
            "4. STALE FOLLOW-UPS — anyone overdue on contact cadence.\n\n"
            "RULES:\n"
            "- Do not invent items not in the pre-fetched data.\n"
            "- If a section has nothing, skip it entirely.\n"
            "- Be direct. No filler. Lead with the most important thing.\n"
            "- Reference people by name, not email address.\n"
            "- The INBOX NEEDING REPLY bucket only contains threads where the\n"
            "  LAST message is not from the user — the ball is already in the\n"
            '  user\'s court. Frame each item as an open ask, not as "verify"\n'
            '  or "confirm you replied".\n'
            "- If a thread isn't in INBOX NEEDING REPLY, the user has replied\n"
            "  (or the thread is archived). Do not recommend further action on\n"
            "  it unless the user explicitly asked about it.\n\n"
            f"--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
        )

        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text or "(no briefing generated)"
