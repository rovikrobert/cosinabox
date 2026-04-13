"""Runtime timezone management with SQLite persistence."""

from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

from cosinabox import defaults

logger = logging.getLogger(__name__)

_timezone: str = defaults.DEFAULT_TIMEZONE


def get_timezone() -> str:
    """Return the current operating timezone (IANA string)."""
    return _timezone


def resolve_timezone(raw: str) -> str | None:
    """Resolve a user-provided timezone string to a valid IANA timezone.

    Handles exact IANA names, underscore normalisation (spaces to _),
    and fuzzy city-name search against the IANA database.
    Returns None if no unambiguous match is found.
    """
    # 1. Exact match
    try:
        ZoneInfo(raw)
        return raw
    except (KeyError, ValueError):
        pass

    # 2. Replace spaces with underscores (e.g. "US/New York" → "US/New_York")
    normalised = raw.replace(" ", "_")
    try:
        ZoneInfo(normalised)
        return normalised
    except (KeyError, ValueError):
        pass

    # 3. Fuzzy search: match city portion case-insensitively
    query = normalised.lower()
    all_tz = available_timezones()
    matches = [tz for tz in all_tz if query in tz.lower()]

    if len(matches) == 1:
        return matches[0]

    # Prefer matches where the city part (after /) matches exactly
    city_matches = [
        tz for tz in matches
        if tz.rsplit("/", 1)[-1].lower() == query.rsplit("/", 1)[-1].lower()
    ]
    if len(city_matches) == 1:
        return city_matches[0]

    return None


def set_timezone(tz: str) -> str:
    """Change operating timezone at runtime.

    Validates the IANA timezone string. Returns the previous timezone.
    Raises KeyError if the timezone is invalid.
    """
    global _timezone
    ZoneInfo(tz)  # validates — raises KeyError if invalid
    prev = _timezone
    _timezone = tz
    return prev


def persist_timezone(tz: str, db_path: Path | None = None) -> None:
    """Write timezone override to SQLite config table."""
    import sqlite3

    if db_path is None:
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("timezone_override", tz),
        )
        conn.commit()
    finally:
        conn.close()


def load_timezone_override(db_path: Path | None = None) -> str | None:
    """Load persisted timezone on boot. Returns the loaded value or None."""
    import sqlite3

    if db_path is None:
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(
                "SELECT value FROM config WHERE key = ?",
                ("timezone_override",),
            )
            row = cur.fetchone()
            if row:
                set_timezone(row[0])
                return row[0]
        finally:
            conn.close()
    except Exception:
        logger.debug("Could not load timezone override", exc_info=True)
    return None
