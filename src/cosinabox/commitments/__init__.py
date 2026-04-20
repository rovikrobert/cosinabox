"""Commitment tracking — structured open-work management.

Ported from cos-agent's ``src/commitments.py`` (2026-04-19). Differences:

- **Sync**, not async. cos-agent ran on asyncpg; cosinabox uses sync SQLite.
- **SQLite**, not Postgres. ``SERIAL`` → ``INTEGER AUTOINCREMENT``,
  ``TIMESTAMPTZ`` → ``TEXT`` (ISO 8601). Schema lives in
  ``cosinabox.memory.sqlite``.
- **OSS-safe defaults**: owner defaults to ``"user"``, not a maintainer name.

Public API:

- ``create_commitment`` / ``get_commitment`` / ``list_commitments``
- ``update_commitment``
- ``close_commitment`` / ``dismiss_commitment`` / ``reopen_commitment``
- ``list_recent_closures``
- ``CommitmentStatus``, ``CommitmentNotFound``, ``CommitmentAlreadyClosed``,
  ``CommitmentNotClosed``

Every call takes a ``Memory`` instance; no module-level connection pool.
"""

from __future__ import annotations

from cosinabox.commitments.models import (
    Commitment,
    CommitmentAlreadyClosed,
    CommitmentNotClosed,
    CommitmentNotFound,
    CommitmentStatus,
)
from cosinabox.commitments.store import (
    close_commitment,
    create_commitment,
    dismiss_commitment,
    get_commitment,
    list_commitments,
    list_recent_closures,
    reopen_commitment,
    update_commitment,
)

__all__ = [
    "Commitment",
    "CommitmentAlreadyClosed",
    "CommitmentNotClosed",
    "CommitmentNotFound",
    "CommitmentStatus",
    "close_commitment",
    "create_commitment",
    "dismiss_commitment",
    "get_commitment",
    "list_commitments",
    "list_recent_closures",
    "reopen_commitment",
    "update_commitment",
]
