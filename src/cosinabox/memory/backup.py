"""Rolling on-disk backups of the SQLite store.

The store holds primary data, not a cache: research signals exist nowhere else
once a digest is delivered. A single volume with no copy makes any loss
unrecoverable, which is why this runs before the weekly job writes.

Uses SQLite's own backup API rather than a file copy so a concurrent writer
cannot produce a torn snapshot.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from cosinabox import defaults

logger = logging.getLogger(__name__)

_SUFFIX = ".bak"


def backup_database(
    db_path: Path, *, keep: int = defaults.MEMORY_BACKUP_KEEP, now: datetime | None = None
) -> Path | None:
    """Write a consistent copy of `db_path` into a sibling `backups/` dir.

    Returns the backup path, or None when there is nothing to back up.
    Prunes to the `keep` most recent copies.
    """
    if not db_path.exists():
        logger.info("No database at %s — nothing to back up", db_path)
        return None

    now = now or datetime.now(tz=None)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = db_path.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{db_path.name}.{stamp}{_SUFFIX}"

    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(out_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    existing = sorted(
        (p for p in out_dir.iterdir() if p.name.startswith(db_path.name) and p.suffix == _SUFFIX),
        key=lambda p: p.name,
    )
    for stale in existing[:-keep] if keep > 0 else existing:
        stale.unlink(missing_ok=True)
        logger.info("Pruned old backup %s", stale.name)

    logger.info("Database backed up to %s", out_path)
    return out_path
