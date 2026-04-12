"""Runtime timezone management with SQLite persistence."""

from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from cosinabox import defaults

logger = logging.getLogger(__name__)

_timezone: str = defaults.DEFAULT_TIMEZONE


def get_timezone() -> str:
    """Return the current operating timezone (IANA string)."""
    return _timezone


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
