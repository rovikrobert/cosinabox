"""Cheap relevance pass between collection and synthesis.

The keyword filter in the collector is deliberately blunt — it matches a
tracked term anywhere in the title or summary, which lets through papers that
name-drop an entity in an unrelated citation. This pass asks the cheapest
model to make that judgement properly.

Fails open by design. Synthesis is prompted never to fabricate, so handing it
a few irrelevant candidates costs tokens; dropping every candidate because the
classifier had a bad minute costs the entire digest.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cosinabox import defaults

logger = logging.getLogger(__name__)

_PROMPT = """You are filtering candidate news items for a research digest.

Tracked entities:
{entities}

Below are numbered candidate items. Return a JSON array of the indices whose
item is genuinely *about* one or more tracked entities — an announcement,
release, hire, funding round, policy change or result involving them.

Exclude items that merely mention an entity in passing (a citation, a
comparison table, an unrelated related-work section).

Return ONLY the JSON array, e.g. [0, 3, 7].

Items:
{items}
"""


def _fenced_blocks(text: str) -> list[str]:
    return [
        m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    ]


def _bare_arrays(text: str) -> list[str]:
    match = re.search(r"\[[\s\d,\-]*\]", text)
    return [match.group()] if match else []


def _extract_indices(text: str) -> list[int] | None:
    """Pull a JSON array of ints out of the response, tolerating prose."""
    for candidate in (text.strip(), *_fenced_blocks(text), *_bare_arrays(text)):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list) and all(isinstance(i, int) for i in parsed):
            return parsed
    return None


def _response_text(response: Any) -> str:
    return "".join(
        block.text
        for block in getattr(response, "content", [])
        if getattr(block, "type", "") == "text"
    )


def classify(
    items: list[dict[str, Any]], *, entity_names: list[str], client: Any
) -> list[dict[str, Any]]:
    """Return the subset of `items` the model judged relevant.

    Returns `items` unchanged on any failure — see the module docstring.
    """
    if not items:
        return []

    listing = "\n".join(
        f"{n}. {i.get('title', '')} — {i.get('snippet', '')[:200]}" for n, i in enumerate(items)
    )
    prompt = _PROMPT.format(
        entities="\n".join(f"- {name}" for name in entity_names),
        items=listing,
    )

    try:
        response = client.messages.create(
            model=defaults.RESEARCH_CLASSIFIER_MODEL,
            max_tokens=defaults.RESEARCH_CLASSIFIER_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Research classifier unavailable (%s) — keeping all candidates", exc)
        return items

    indices = _extract_indices(_response_text(response))
    if indices is None:
        logger.warning("Research classifier returned no parseable indices — keeping all candidates")
        return items

    kept = [items[i] for i in indices if 0 <= i < len(items)]
    logger.info("Research classifier kept %d of %d candidates", len(kept), len(items))
    return kept
