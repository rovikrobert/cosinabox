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
        db: Any | None = None,
        attio: Any | None = None,
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.stakeholders = stakeholders or []
        self.db = db
        self.attio = attio

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

        # Commitment verification — grounds PRIORITIES in GENUINELY OPEN.
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
                pass

        # Keep Warm — Attio-curated overdue relationships. Grounded data
        # only; quiet when no one is overdue (don't announce "no overdue"
        # and crowd the briefing).
        if self.attio is not None:
            try:
                from cosinabox.defaults import KEEP_WARM_MAX_BRIEFING_ROWS

                overdue = self.attio.get_keep_warm_overdue()
                if overdue:
                    lines = []
                    for p in overdue[:KEEP_WARM_MAX_BRIEFING_ROWS]:
                        note_part = f". Note: {p.note}" if p.note else ""
                        lines.append(
                            f"- {p.name} — {p.days_since}d since last contact "
                            f"(cadence: {p.cadence_days}d){note_part}"
                        )
                    sections.append("KEEP WARM — OVERDUE:\n" + "\n".join(lines))
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

        priorities_rule = (
            "3. PRIORITIES — top 3 items from GENUINELY OPEN, ordered by\n"
            "   (deadline ascending, priority ascending). If GENUINELY OPEN is\n"
            "   empty or missing, skip the PRIORITIES section — do NOT infer\n"
            "   priorities from calendar or email signals.\n"
            if self.db is not None
            else "3. PRIORITIES — top 3 based on calendar + email signals.\n"
        )

        commitment_rules = (
            "- If COMMITMENT VERIFICATION shows VERIFIED DONE → NEVER list\n"
            "  as a priority. LIKELY DONE → treat as done.\n"
            "- Only GENUINELY OPEN commitments can appear in PRIORITIES.\n"
            if self.db is not None
            else ""
        )

        keep_warm_rule = (
            "5. KEEP WARM — overdue relationships from the curated list\n"
            "   (see pre-fetched KEEP WARM — OVERDUE). Reference people by\n"
            "   name only; never mention record IDs. Skip this section if\n"
            "   KEEP WARM — OVERDUE is absent.\n"
            if self.attio is not None
            else ""
        )

        prompt = (
            f"Generate {self.name_for_briefing}'s morning briefing for TODAY: {today}.\n\n"
            "FORMAT: Max 25 lines. One line per item. Skip empty sections.\n"
            "1. SCHEDULE — meetings with times. Flag any needing prep.\n"
            "2. EMAIL — items where the ball is in the user's court.\n"
            "   Only surface threads from INBOX NEEDING REPLY. For each, lead with\n"
            "   the pending ask; don't recommend actions the user already took.\n"
            f"{priorities_rule}"
            "4. STALE FOLLOW-UPS — anyone overdue on contact cadence.\n"
            f"{keep_warm_rule}"
            "\n"
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
            "  it unless the user explicitly asked about it.\n"
            f"{commitment_rules}"
            f"\n--- PRE-FETCHED DATA ---\n{prefetched}\n--- END ---"
        )

        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text or "(no briefing generated)"
