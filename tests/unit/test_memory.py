from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from cosinabox.memory.sqlite import Memory


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


def test_store_and_recent(memory: Memory) -> None:
    memory.store_message(role="user", content="hello", session_id="s1")
    memory.store_message(role="assistant", content="hi back", session_id="s1")
    msgs = memory.recent_messages(session_id="s1", limit=10)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "hi back"


def test_session_isolation(memory: Memory) -> None:
    memory.store_message(role="user", content="A", session_id="s1")
    memory.store_message(role="user", content="B", session_id="s2")
    assert len(memory.recent_messages(session_id="s1")) == 1
    assert memory.recent_messages(session_id="s1")[0]["content"] == "A"


def test_clear_old(memory: Memory) -> None:
    from datetime import datetime, timedelta

    old = datetime.now(UTC) - timedelta(days=45)
    memory.store_message(role="user", content="ancient", session_id="s1", timestamp=old)
    memory.store_message(role="user", content="fresh", session_id="s1")
    memory.clear_old(older_than_days=30)
    msgs = memory.recent_messages(session_id="s1")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "fresh"
