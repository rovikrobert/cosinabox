from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from cosinabox.memory.backup import backup_database

NOW = datetime(2026, 8, 20, 3, 4, 5, tzinfo=UTC)


def _db(tmp_path, name="memory.db"):
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return path


def test_creates_a_timestamped_copy_that_opens(tmp_path):
    src = _db(tmp_path)
    out = backup_database(src, keep=3, now=NOW)
    assert out is not None
    assert out.name == "memory.db.20260820T030405Z.bak"
    assert out.parent == src.parent / "backups"
    conn = sqlite3.connect(out)
    assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    conn.close()


def test_missing_source_returns_none(tmp_path):
    assert backup_database(tmp_path / "nope.db", keep=3, now=NOW) is None


def test_prunes_to_the_keep_count_oldest_first(tmp_path):
    src = _db(tmp_path)
    made = []
    for minute in range(5):
        made.append(backup_database(src, keep=3, now=NOW.replace(minute=minute)))
    remaining = sorted(p.name for p in (src.parent / "backups").iterdir())
    assert len(remaining) == 3
    # The three most recent survive.
    assert remaining == sorted(p.name for p in made[-3:])
