"""Core system prompt template."""

from __future__ import annotations

from jinja2 import Template

_SYSTEM_PROMPT_SRC = (
    "You are {{ name }}'s Chief of Staff.\n"
    "\n"
    "Timezone: {{ timezone }}\n"
    "\n"
    "Personality:\n"
    "{{ personality }}\n"
    "\n"
    "Be direct. Surface conflicts before they're asked about. "
    "If you're confident, act; if not, ask one tight question."
)

_SYSTEM_PROMPT = Template(_SYSTEM_PROMPT_SRC)


def render_system_prompt(*, personality: str, name: str, timezone: str) -> str:
    return _SYSTEM_PROMPT.render(
        personality=personality, name=name, timezone=timezone
    )
