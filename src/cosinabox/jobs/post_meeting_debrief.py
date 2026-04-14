"""Post-meeting debrief — detect ended meetings, fetch transcripts, send summary."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)


def _transcript_matches(
    transcript: dict[str, Any],
    *,
    cal_title: str,
    cal_emails: set[str],
    cal_start: datetime,
) -> bool:
    t_title = (transcript.get("title") or "").lower()
    cal_lower = cal_title.lower()
    criteria_met = 0

    title_substring = cal_lower in t_title or t_title in cal_lower
    if title_substring:
        criteria_met += 1

    cal_words = {w for w in cal_lower.split() if len(w) > 2}
    t_words = {w for w in t_title.split() if len(w) > 2}
    # Only count word overlap if substring check didn't already match
    if not title_substring and cal_words & t_words:
        criteria_met += 1

    t_participants = {(p or "").lower() for p in (transcript.get("participants") or [])}
    if cal_emails & t_participants:
        criteria_met += 1

    t_date = transcript.get("date", "")
    if t_date:
        try:
            t_dt = datetime.fromisoformat(t_date.replace("Z", "+00:00"))
            if t_dt.tzinfo is None:
                t_dt = t_dt.replace(tzinfo=UTC)
            if abs((t_dt - cal_start).total_seconds()) < 1800:
                criteria_met += 1
        except (ValueError, TypeError):
            pass

    is_generic = len(cal_lower.split()) <= 1
    if is_generic:
        return criteria_met >= 2
    return criteria_met >= 1


class PostMeetingDebriefJob(Job):
    name = "post_meeting_debrief"

    def __init__(
        self,
        *,
        calendar: Any | None,
        fireflies: Any | None,
        db: Any,
        send_fn: Callable[[str], None],
        skip_titles: list[str] | None = None,
        rela: Any | None = None,
    ) -> None:
        self.calendar = calendar
        self.fireflies = fireflies
        self.db = db
        self.send_fn = send_fn
        self.skip_titles = [t.lower() for t in (skip_titles or [])]
        self.rela = rela

    def _is_debriefed(self, uid: str) -> bool:
        cur = self.db._conn.execute(
            "SELECT 1 FROM debrief_state WHERE ical_uid = ?", (uid,),
        )
        return cur.fetchone() is not None

    def _mark_debriefed(self, uid: str) -> None:
        ts = datetime.now(UTC).isoformat()
        self.db._conn.execute(
            "INSERT OR IGNORE INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            (uid, ts),
        )
        self.db._conn.commit()

    def run(self, context: Any = None) -> str:
        if self.calendar is None:
            return "Calendar not configured — skipped"

        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=30)
        window_end = now - timedelta(minutes=15)
        search_start = window_start - timedelta(hours=2)
        events = self.calendar.list_events(start=search_start, end=window_end)

        debriefed = 0
        for evt in events:
            uid = evt.id
            if self._is_debriefed(uid):
                continue
            if not (window_start <= evt.end <= window_end):
                continue
            if any(skip in evt.summary.lower() for skip in self.skip_titles):
                self._mark_debriefed(uid)
                continue

            lines = [f"Meeting just ended: {evt.summary}"]

            if self.fireflies is not None:
                try:
                    transcripts = self.fireflies.list_recent_meetings(hours=24)
                    cal_emails: set[str] = {a.lower() for a in (evt.attendees or [])}
                    candidates = [
                        t for t in transcripts
                        if _transcript_matches(
                            t, cal_title=evt.summary,
                            cal_emails=cal_emails, cal_start=evt.start,
                        )
                    ]
                    if candidates:
                        best = candidates[0]
                        t_data = self.fireflies.get_transcript(best["id"])
                        sentences = t_data.get("sentences") or []
                        if sentences:
                            overview = " ".join(s.get("text", "") for s in sentences[:10])
                            lines.append(f"\nKey points:\n{overview[:800]}")
                        lines.append("\nTranscript captured by Fireflies.")
                    else:
                        lines.append("\nNo transcript found yet (may still be processing).")
                except Exception:
                    logger.warning("Fireflies lookup failed for %s", evt.summary, exc_info=True)
                    lines.append("\nTranscript lookup failed.")
            else:
                lines.append("\nFireflies not configured — no transcript available.")

            lines.append("\nAnything to add? Decisions, next steps, things that changed?")

            self.send_fn("\n".join(lines))
            self._mark_debriefed(uid)
            debriefed += 1

            if self.rela is not None:
                try:
                    self.rela.ingest(f"Meeting ended: {evt.summary}. " + "\n".join(lines))
                except Exception:
                    logger.debug("Rela feed failed for %s", evt.summary, exc_info=True)

        return f"Debriefed {debriefed} meetings"
