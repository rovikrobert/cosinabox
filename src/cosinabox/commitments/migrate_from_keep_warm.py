"""Keep Warm note ↔ commitments migration — detector and flagged-row query.

Detection (`looks_like_commitment`) is a pure-string regex operating on
free-text notes. Migration extraction (turning a flagged note into
structured commitments) happens in the agent loop, not here — the
`list_flagged_keep_warm_notes` helper just identifies which notes need
review so the agent can reason about each one conversationally.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Case-insensitive. Each alternative is a complete commitment-shaped
# phrase. Bias is toward false positives (soft-warn semantics); false
# negatives let leaks continue accumulating.
_WEEKDAY = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?"
_MONTH = (
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?"
)
_ACTION = (
    r"(?:send|reply|respond|share|submit|deliver|follow[\s-]?up|email|call|"
    r"ping|sign)"
)

_COMMITMENT_PATTERNS = [
    # "by <weekday>", "before <weekday>", "on <weekday>"
    # Known FP: bare "on <weekday>" fires on biographical/past-tense mentions
    # ("met on Friday", "born on Tuesday"). Accepted under soft-warn semantics —
    # cost is a dismissable warning, not a blocked write.
    rf"\b(?:by|before|on|this|next)\s+{_WEEKDAY}\b",
    # "by EOD", "before EOW", "by EOM"
    r"\b(?:by|before)\s+(?:EO[DWM])\b",
    # "this week", "next week", "this month", "next month"
    # Known FP: "she leads next quarter's fundraise" would fire on "next quarter".
    # Acceptable under soft-warn.
    r"\b(?:this|next)\s+(?:week|month|quarter)\b",
    # "in 3 days", "in 2 weeks", "in a month"
    r"\bin\s+(?:\d+|a|an|one|two|three|four|five)\s+(?:day|week|month)s?\b",
    # "by Q1".."by Q4"
    r"\bby\s+Q[1-4]\b",
    # "by <Month> <day>" e.g. "by Jan 15", "by March 15"
    rf"\bby\s+{_MONTH}\s+\d{{1,2}}\b",
    # Action verb + time-ish: "send X by", "reply X before"
    # Bound window to 40 chars to avoid matching across unrelated clauses
    rf"\b{_ACTION}\b[^.!?\n]{{0,40}}?\b(?:by|before|this|next|in)\b",
    # Action verb + weekday: "follow up on Friday"
    rf"\b{_ACTION}\b[^.!?\n]{{0,40}}?\b(?:on|this|next|by|before)?\s*{_WEEKDAY}\b",
]

_COMBINED = re.compile("|".join(_COMMITMENT_PATTERNS), re.IGNORECASE)


def looks_like_commitment(text: str | None) -> str | None:
    """Return the matched substring if ``text`` looks commitment-shaped, else None.

    The returned substring is the first match — used for the user-facing
    warning so they can see which phrase tripped the detector.
    """
    if not text or not text.strip():
        return None
    m = _COMBINED.search(text)
    return m.group(0) if m else None


def list_flagged_keep_warm_notes(attio: Any) -> list[dict[str, Any]]:
    """Return keep-warm people whose notes trip `looks_like_commitment`.

    Read-only: the agent loop walks the returned list to propose
    extractions conversationally. On any Attio error, returns [] — we
    never raise from this tool surface.
    """
    try:
        people = attio.list_keep_warm()
    except Exception:
        logger.warning("list_flagged_keep_warm_notes: Attio query failed", exc_info=True)
        return []

    flagged: list[dict[str, Any]] = []
    for p in people:
        note = getattr(p, "note", None)
        matches = _COMBINED.findall(note) if note else []
        if not matches:
            continue
        flagged.append(
            {
                "person": getattr(p, "name", ""),
                "record_id": getattr(p, "record_id", ""),
                "note": note,
                "regex_matches": matches,
                "days_since": getattr(p, "days_since", None),
                "cadence_days": getattr(p, "cadence_days", None),
            }
        )
    return flagged
