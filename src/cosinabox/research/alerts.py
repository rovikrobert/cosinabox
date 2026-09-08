"""Post-synthesis health checks.

"The job ran" is not a success signal. Both shapes below were recorded in the
legacy system's job history when they happened, and neither alerted — so a
failed digest sat unnoticed for two weeks until the next one failed the same
way. These checks exist to turn that silence into a page.
"""

from __future__ import annotations

from cosinabox import defaults
from cosinabox.research.synthesizer import SYNTHESIS_FAILED_NOTICE


def synthesis_alerts(*, telegram_summary: str, signal_count: int, raw_length: int) -> list[str]:
    """Reasons this run deserves a human look. Empty when healthy."""
    alerts: list[str] = []

    if telegram_summary.strip().startswith(SYNTHESIS_FAILED_NOTICE):
        alerts.append(
            f"Synthesis produced no parseable output ({raw_length} chars). "
            "The digest shipped the failure notice."
        )
    elif signal_count == 0:
        # A quiet week is legitimate, but it looks identical to a silent
        # regression, so it is worth one glance either way.
        alerts.append(
            f"Synthesis parsed cleanly but found 0 signals ({raw_length} chars). "
            "Either a genuinely quiet week or a silent regression."
        )

    budget = defaults.RESEARCH_SYNTHESIS_MAX_TOKENS * defaults.RESEARCH_SYNTHESIS_CHARS_PER_TOKEN
    if raw_length >= budget * defaults.RESEARCH_SYNTHESIS_WARN_RATIO:
        alerts.append(
            f"Synthesis output is {raw_length} chars, {raw_length / budget:.0%} of the "
            f"~{int(budget)}-char ceiling. Trim the prompt's output contract "
            "before it truncates."
        )

    return alerts
