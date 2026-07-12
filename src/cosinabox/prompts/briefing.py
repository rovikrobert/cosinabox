"""Morning briefing prompt template."""

from __future__ import annotations

from jinja2 import Template

_BRIEFING_PROMPT_SRC = (
    "Compose {{ name }}'s morning briefing.\n"
    "\n"
    "Personality:\n"
    "{{ personality }}\n"
    "\n"
    "## Calendar\n"
    "{{ calendar_summary }}\n"
    "\n"
    "## Email\n"
    "{{ email_summary }}\n"
    "\n"
    "## Follow-ups\n"
    "{{ followups }}\n"
    "\n"
    "Format the output as a single Telegram message: short, scannable, opinionated. "
    "Surface conflicts. Don't recap things {{ name }} already knows."
)

_BRIEFING_PROMPT = Template(_BRIEFING_PROMPT_SRC)


def render_briefing_prompt(
    *,
    personality: str,
    name: str,
    calendar_summary: str,
    email_summary: str,
    followups: str,
) -> str:
    # See prompts/core.py — jinja2 stubs type Template.render() as Any.
    return str(
        _BRIEFING_PROMPT.render(
            personality=personality,
            name=name,
            calendar_summary=calendar_summary,
            email_summary=email_summary,
            followups=followups,
        )
    )
