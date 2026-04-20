"""Auto-resolution layer for open commitments — ported from cos-agent.

For each open commitment, search recent sent mail for evidence that it's
been completed. Tags each commitment with one of:

- ``VERIFIED_DONE`` — strong evidence (2+ distinct keywords hit in one
  subject line).
- ``LIKELY_DONE`` — weak evidence (a single keyword match in a subject).
- ``NO_EVIDENCE`` — nothing found in the lookback window.

Briefings treat ``VERIFIED_DONE`` as closed (don't list as carry-over)
even if the row still has ``status='open'``; ``LIKELY_DONE`` is
surfaced with a "confirm with user" framing. Only ``NO_EVIDENCE``
items can appear in carry-over / next-week / priorities sections.

Drive search is not in this port — see the plan doc.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeout
from datetime import UTC, datetime
from typing import Any

from cosinabox import defaults
from cosinabox.commitments.store import list_commitments
from cosinabox.memory import Memory

logger = logging.getLogger(__name__)


VERDICT_VERIFIED_DONE = "VERIFIED_DONE"
VERDICT_LIKELY_DONE = "LIKELY_DONE"
VERDICT_NO_EVIDENCE = "NO_EVIDENCE"


_STOP_WORDS = frozenset(
    {
        # articles, prepositions, basic verbs
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "is",
        "was",
        "be",
        "at",
        "by",
        "from",
        "up",
        "as",
        "if",
        "but",
        # email metadata
        "re",
        "fw",
        "fwd",
        # generic action verbs (not distinctive)
        "follow",
        "send",
        "check",
        "get",
        "push",
        "draft",
        "review",
        "schedule",
        "plan",
        "coordinate",
        "confirm",
        "organize",
        "develop",
        "work",
        "make",
        "do",
        "ensure",
        "ask",
        "tell",
        "give",
        "take",
        # generic nouns (not distinctive)
        "it",
        "this",
        "that",
        "these",
        "those",
        "us",
        "we",
        "our",
    }
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _extract_keywords(title: str, stakeholder: str | None = None) -> list[str]:
    """Pull distinctive keywords from a commitment title.

    - First keyword is the stakeholder's first name (if any).
    - Then up to 4 content keywords, stop-words filtered, acronyms kept.
    """
    keywords: list[str] = []
    if stakeholder:
        first = stakeholder.split()[0].strip()
        if first:
            keywords.append(first.lower())

    for w in re.findall(r"[a-zA-Z]{2,}", title.lower()):
        if w in _STOP_WORDS or w in keywords:
            continue
        keywords.append(w)
        if len(keywords) >= 5:
            break

    return keywords


def _sanitize_query(query: str) -> str:
    """Strip Gmail operators/quotes so we pass the search as plain text."""
    cleaned = re.sub(r"[():\"']", " ", query)
    cleaned = re.sub(
        r"\b(OR|AND|NOT|from|to|subject|in|is|has)\b:?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split())


def _has_real_match(messages: list[Any], keywords: list[str], min_matches: int = 2) -> bool:
    """True iff ≥1 message's subject contains ≥ ``min_matches`` distinct keywords."""
    if not messages or not keywords:
        return False
    for m in messages:
        subject = getattr(m, "subject", "") or ""
        subject_lc = subject.lower()
        hits = 0
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", subject_lc):
                hits += 1
                if hits >= min_matches:
                    return True
    return False


def _has_single_keyword_match(messages: list[Any], keywords: list[str]) -> bool:
    """True iff any subject contains at least one keyword (weaker signal)."""
    if not messages or not keywords:
        return False
    for m in messages:
        subject_lc = (getattr(m, "subject", "") or "").lower()
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", subject_lc):
                return True
    return False


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


def verify_commitment(
    commitment: dict[str, Any],
    gmail: Any,
    *,
    db: Memory | None = None,
    lookback_days: int = defaults.AUTO_RESOLVE_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Search sent mail for evidence a commitment is done.

    Returns the commitment dict with ``_verdict`` and ``_evidence`` added.
    If ``db`` is supplied, persists ``last_verdict`` + ``last_verdict_at``.
    """
    title = commitment.get("title", "")
    description = commitment.get("description") or ""
    stakeholder = commitment.get("stakeholder")

    title_kw = _extract_keywords(title, stakeholder)
    desc_kw = _extract_keywords(description) if description else []

    seen: set[str] = set()
    keywords: list[str] = []
    for k in title_kw + desc_kw:
        if k not in seen:
            seen.add(k)
            keywords.append(k)

    if not keywords:
        return _record(commitment, VERDICT_NO_EVIDENCE, "no search terms", db=db)

    query = _sanitize_query(" ".join(keywords[:4]))
    full_query = f"newer_than:{lookback_days}d in:sent {query}"

    try:
        messages = gmail.search(full_query, max_results=5)
    except Exception as e:
        logger.debug("auto_resolve: gmail.search raised %s", e)
        return _record(
            commitment,
            VERDICT_NO_EVIDENCE,
            f"error: {type(e).__name__}",
            db=db,
        )

    if _has_real_match(messages, keywords, min_matches=2):
        return _record(
            commitment,
            VERDICT_VERIFIED_DONE,
            f"sent mail subject match '{query}' (last {lookback_days}d)",
            db=db,
        )
    if _has_single_keyword_match(messages, keywords):
        return _record(
            commitment,
            VERDICT_LIKELY_DONE,
            f"weak sent mail match '{query}' (last {lookback_days}d)",
            db=db,
        )

    return _record(
        commitment,
        VERDICT_NO_EVIDENCE,
        f"no match for '{query}' in {lookback_days}d",
        db=db,
    )


def _record(
    commitment: dict[str, Any],
    verdict: str,
    evidence: str,
    *,
    db: Memory | None,
) -> dict[str, Any]:
    """Attach verdict + evidence to the dict; persist if db is provided."""
    commitment_id = commitment.get("id")
    if db is not None and commitment_id is not None:
        try:
            db._conn.execute(
                "UPDATE commitments SET last_verdict = ?, last_verdict_at = ? WHERE id = ?",
                (verdict, datetime.now(UTC).isoformat(), commitment_id),
            )
            db._conn.commit()
        except Exception:
            logger.warning(
                "auto_resolve: could not persist verdict for #%s",
                commitment_id,
                exc_info=True,
            )
    return {**commitment, "_verdict": verdict, "_evidence": evidence}


def verify_all_open_commitments(
    db: Memory,
    gmail: Any,
    *,
    limit: int = defaults.AUTO_RESOLVE_MAX_ITEMS,
    concurrency: int = defaults.AUTO_RESOLVE_CONCURRENCY,
    timeout_per_item_s: int = defaults.AUTO_RESOLVE_TIMEOUT_PER_ITEM_S,
) -> list[dict[str, Any]]:
    """Verify every open commitment in parallel. Returns the enriched list.

    Per-item timeout ensures one slow Gmail search doesn't block others;
    errors/timeouts tag the item ``NO_EVIDENCE`` with an explanatory
    evidence string so briefings render something sensible.
    """
    open_items = list_commitments(db, limit=limit)
    if not open_items:
        return []

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_item = {pool.submit(verify_commitment, c, gmail, db=db): c for c in open_items}
        for fut, c in future_to_item.items():
            try:
                results.append(fut.result(timeout=timeout_per_item_s))
            except _FutureTimeout:
                results.append(
                    {**c, "_verdict": VERDICT_NO_EVIDENCE, "_evidence": "verification timed out"}
                )
            except Exception as e:
                results.append({**c, "_verdict": VERDICT_NO_EVIDENCE, "_evidence": f"error: {e}"})

    # Preserve the original list order (ThreadPoolExecutor returns
    # completion-order). Use the original commitment id order.
    id_order = [c["id"] for c in open_items]
    results.sort(key=lambda r: id_order.index(r["id"]) if r["id"] in id_order else 999)
    return results


# ---------------------------------------------------------------------------
# Briefing formatter
# ---------------------------------------------------------------------------


def format_for_briefing(verified: list[dict[str, Any]]) -> str:
    """Format verified commitments for injection into briefing prompts.

    Groups by verdict so the model sees clear signals about what's open.
    """
    if not verified:
        return ""

    done = [c for c in verified if c.get("_verdict") == VERDICT_VERIFIED_DONE]
    likely = [c for c in verified if c.get("_verdict") == VERDICT_LIKELY_DONE]
    open_items = [c for c in verified if c.get("_verdict") == VERDICT_NO_EVIDENCE]

    sections = ["COMMITMENT VERIFICATION (auto-checked against Gmail):"]

    if done:
        sections.append("\nVERIFIED DONE — DO NOT list as carry-over (auto-detected):")
        for c in done:
            sections.append(f"  ✓ #{c['id']} {c['title']} — {c.get('_evidence', '')}")

    if likely:
        sections.append(
            "\nLIKELY DONE — confirm with user, treat as not-pending unless they object:"
        )
        for c in likely:
            sections.append(f"  ? #{c['id']} {c['title']} — {c.get('_evidence', '')}")

    if open_items:
        sections.append("\nGENUINELY OPEN — no evidence of completion in the lookback window:")
        for c in open_items:
            stakeholder = f" [{c['stakeholder']}]" if c.get("stakeholder") else ""
            priority = c.get("priority", "?")
            sections.append(f"  ○ #{c['id']} P{priority}: {c['title']}{stakeholder}")

    return "\n".join(sections)
