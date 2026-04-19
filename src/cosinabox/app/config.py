"""Config loading — personality, jobs, integrations."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from cosinabox import defaults

logger = logging.getLogger("cosinabox")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


def load_personality(config_dir: Path) -> tuple[str, str, str]:
    """Returns (body, name, timezone).

    Kept tuple-returning for backwards compat. Callers that need the
    optional ``event_relevance`` allowlist should call
    ``load_personality_frontmatter`` instead — it returns the full parsed
    frontmatter dict.
    """
    path = config_dir / "personality.md"
    if not path.exists():
        logger.warning("personality.md not found in %s", config_dir)
        return "(no personality)", "user", defaults.DEFAULT_TIMEZONE
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, "user", defaults.DEFAULT_TIMEZONE
    front: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    return (
        m.group(2).strip(),
        front.get("name", "user"),
        front.get("timezone", defaults.DEFAULT_TIMEZONE),
    )


def load_personality_frontmatter(config_dir: Path) -> dict[str, Any]:
    """Parse personality.md frontmatter into a dict. Returns ``{}`` if the
    file or frontmatter is missing. Intended for optional fields like
    ``event_relevance`` that newer jobs need without breaking older
    callers of ``load_personality``.
    """
    path = config_dir / "personality.md"
    if not path.exists():
        return {}
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    front: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    return front


def load_jobs(config_dir: Path) -> dict[str, Any]:
    """Load jobs.yaml from config_dir."""
    path = config_dir / "jobs.yaml"
    if not path.exists():
        logger.warning("jobs.yaml not found in %s", config_dir)
        return {}
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    jobs = data.get("jobs", {})
    return jobs if isinstance(jobs, dict) else {}


def load_integrations(config_dir: Path) -> dict[str, Any]:
    """Load integrations.yaml from config_dir."""
    path = config_dir / "integrations.yaml"
    if not path.exists():
        return {}
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    integrations = data.get("integrations", {})
    return integrations if isinstance(integrations, dict) else {}
