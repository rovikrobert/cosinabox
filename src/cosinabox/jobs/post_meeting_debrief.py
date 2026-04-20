"""Post-meeting debrief — detect ended meetings, fetch transcripts, send summary."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox import defaults
from cosinabox.jobs._meeting_filter import is_prep_worthy
from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)


# Telegram hard-caps a single message at 4096 chars. We leave headroom for
# header lines and the trailing prompt so we don't have to re-wrap.
_TELEGRAM_MAX_BODY_CHARS = 3500


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _email_local_part(email: str) -> str:
    # "alice@example.com" -> "alice". Empty-string-safe.
    return (email or "").split("@", 1)[0].lower()


def _owner_first_names(owner_emails: Iterable[str]) -> set[str]:
    """Best-effort first-name extraction from owner email local parts.

    "alice@x.com" -> {"alice"}; "alice.smith@x.com" -> {"alice", "smith"};
    "alice+work@x.com" -> {"alice", "work"}. We split on common separators
    so an owner whose local part is "first.last" doesn't accidentally
    let "last" through the title overlap check.
    """
    names: set[str] = set()
    for e in owner_emails:
        local = _email_local_part(e)
        if not local:
            continue
        for part in re.split(r"[._+-]", local):
            if len(part) > 2:
                names.add(part.lower())
    return names


def _transcript_matches(
    transcript: dict[str, Any],
    *,
    cal_title: str,
    cal_emails: set[str],
    cal_start: datetime,
    cal_end: datetime,
    owner_emails: set[str],
) -> bool:
    """Decide whether ``transcript`` belongs to the calendar event.

    Required: transcript date is within ``TRANSCRIPT_TIME_WINDOW_SECONDS``
    of either ``cal_start`` or ``cal_end``. Missing or unparseable date
    means no match — we never fall back to attendee-only matching, which
    would cross-match meetings the owner is in.

    Plus at least one of:
      - title substring (case-insensitive, either direction)
      - title word overlap (>2 chars), excluding the owner's own
        first-name fragments (e.g. ``alice`` from ``alice@x.com``)
      - attendee email overlap, excluding the owner's own emails
    """
    t_dt = _parse_iso_date(transcript.get("date"))
    if t_dt is None:
        return False
    window = defaults.TRANSCRIPT_TIME_WINDOW_SECONDS
    near_start = abs((t_dt - cal_start).total_seconds()) <= window
    near_end = abs((t_dt - cal_end).total_seconds()) <= window
    if not (near_start or near_end):
        return False

    t_title = (transcript.get("title") or "").lower()
    cal_lower = cal_title.lower()

    if cal_lower and (cal_lower in t_title or (t_title and t_title in cal_lower)):
        return True

    owner_names = _owner_first_names(owner_emails)
    cal_words = {w for w in cal_lower.split() if len(w) > 2 and w not in owner_names}
    t_words = {w for w in t_title.split() if len(w) > 2 and w not in owner_names}
    if cal_words & t_words:
        return True

    owner_lower = {e.lower() for e in owner_emails}
    cal_non_owner = {e for e in cal_emails if e not in owner_lower}
    t_participants = {(p or "").lower() for p in (transcript.get("participants") or [])}
    t_non_owner = {p for p in t_participants if p not in owner_lower}
    return bool(cal_non_owner & t_non_owner)


def _pick_best_transcript(
    candidates: list[dict[str, Any]],
    *,
    cal_start: datetime,
    cal_end: datetime,
) -> dict[str, Any]:
    """Pick the single best transcript when multiple candidates match.

    Primary key: distance from ``cal_start`` (smaller is better).
    Secondary key: transcript ``duration`` (larger is better — typically
    the longer recording is the one that actually captured the meeting).
    """
    del cal_end  # reserved for future use

    def sort_key(t: dict[str, Any]) -> tuple[float, float]:
        t_dt = _parse_iso_date(t.get("date"))
        distance = float("inf") if t_dt is None else abs((t_dt - cal_start).total_seconds())
        # negate duration so larger durations sort earlier in ascending order
        duration = float(t.get("duration") or 0)
        return (distance, -duration)

    return min(candidates, key=sort_key)


def _split_for_telegram(body: str, *, max_chars: int = _TELEGRAM_MAX_BODY_CHARS) -> list[str]:
    """Split a long body into Telegram-safe chunks at sentence boundaries.

    We split on existing newlines first (paragraphs), then on sentence
    terminators within a paragraph if a paragraph is itself too long.
    Never breaks mid-sentence — if a single sentence exceeds the limit
    we let it through as its own chunk and trust Telegram to error
    visibly rather than silently mutilate the content.
    """
    if len(body) <= max_chars:
        return [body]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current.rstrip())
            current = ""

    # First pass: paragraphs (split on blank-line-ish boundaries via newlines)
    for paragraph in body.split("\n"):
        candidate = (current + "\n" + paragraph) if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        # Paragraph won't fit — flush whatever we have, then split sentences.
        flush()
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        # Sentence-level split: keep terminators with the preceding sentence.
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        for sentence in sentences:
            cand2 = (current + " " + sentence) if current else sentence
            if len(cand2) <= max_chars:
                current = cand2
            else:
                flush()
                current = sentence
    flush()
    return chunks


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
        relevance_keywords: list[str] | None = None,
        relevance_domains: list[str] | None = None,
        owner_emails: list[str] | None = None,
    ) -> None:
        self.calendar = calendar
        self.fireflies = fireflies
        self.db = db
        self.send_fn = send_fn
        self.skip_titles = [t.lower() for t in (skip_titles or [])]
        self.rela = rela
        self.relevance_keywords = list(relevance_keywords or [])
        self.relevance_domains = list(relevance_domains or [])
        # Lower-cased set for cheap membership checks during matching.
        self.owner_emails: set[str] = {e.lower() for e in (owner_emails or [])}

    def _is_debriefed(self, uid: str) -> bool:
        cur = self.db._conn.execute(
            "SELECT 1 FROM debrief_state WHERE ical_uid = ?",
            (uid,),
        )
        return cur.fetchone() is not None

    def _mark_debriefed(self, uid: str) -> None:
        ts = datetime.now(UTC).isoformat()
        self.db._conn.execute(
            "INSERT OR IGNORE INTO debrief_state (ical_uid, debriefed_at) VALUES (?, ?)",
            (uid, ts),
        )
        self.db._conn.commit()

    def _send_body(self, body: str) -> None:
        for chunk in _split_for_telegram(body):
            self.send_fn(chunk)

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
            if not is_prep_worthy(
                evt,
                skip_titles=self.skip_titles,
                relevance_keywords=self.relevance_keywords,
                relevance_domains=self.relevance_domains,
            ):
                # Solo block, personal pattern, or user skip — no debrief.
                # Mark it so we don't re-evaluate every poll cycle.
                self._mark_debriefed(uid)
                continue

            lines = [f"Meeting just ended: {evt.summary}"]

            if self.fireflies is not None:
                try:
                    transcripts = self.fireflies.list_recent_meetings(hours=24)
                    cal_emails: set[str] = {a.lower() for a in (evt.attendees or [])}
                    candidates = [
                        t
                        for t in transcripts
                        if _transcript_matches(
                            t,
                            cal_title=evt.summary,
                            cal_emails=cal_emails,
                            cal_start=evt.start,
                            cal_end=evt.end,
                            owner_emails=self.owner_emails,
                        )
                    ]
                    if candidates:
                        best = _pick_best_transcript(
                            candidates,
                            cal_start=evt.start,
                            cal_end=evt.end,
                        )
                        t_data = self.fireflies.get_transcript(best["id"])
                        sentences = t_data.get("sentences") or []
                        if sentences:
                            overview = " ".join(s.get("text", "") for s in sentences[:10])
                            lines.append(f"\nKey points:\n{overview}")
                        lines.append("\nTranscript captured by Fireflies.")
                    else:
                        lines.append("\nNo transcript found yet (may still be processing).")
                except Exception:
                    logger.warning("Fireflies lookup failed for %s", evt.summary, exc_info=True)
                    lines.append("\nTranscript lookup failed.")
            else:
                lines.append("\nFireflies not configured — no transcript available.")

            lines.append("\nAnything to add? Decisions, next steps, things that changed?")

            self._send_body("\n".join(lines))
            self._mark_debriefed(uid)
            debriefed += 1

            if self.rela is not None:
                try:
                    self.rela.ingest(f"Meeting ended: {evt.summary}. " + "\n".join(lines))
                except Exception:
                    logger.debug("Rela feed failed for %s", evt.summary, exc_info=True)

        return f"Debriefed {debriefed} meetings"
