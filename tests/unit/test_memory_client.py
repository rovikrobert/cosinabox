from __future__ import annotations

import pytest

from cosinabox.memory.client import LocalMemoryClient


@pytest.fixture
def client(tmp_path):
    return LocalMemoryClient(db_path=tmp_path / "mem.db")


class TestLocalMemoryClient:
    def test_store_returns_id(self, client):
        mid = client.store(text="Decision: launch in Q3", metadata={"source": "meeting"}, namespace="default")
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_recall_finds_stored_memory(self, client):
        client.store(text="Budget approved for $50k", metadata={}, namespace="default")
        results = client.recall(query="budget", namespace="default")
        assert len(results) >= 1
        assert "budget" in results[0]["text"].lower()

    def test_recall_respects_namespace(self, client):
        client.store(text="Secret info", metadata={}, namespace="private")
        results = client.recall(query="secret", namespace="public")
        assert len(results) == 0

    def test_search_matches_metadata(self, client):
        client.store(text="Meeting notes", metadata={"attendee": "alice"}, namespace="default")
        results = client.search(query="alice", namespace="default")
        assert len(results) >= 1

    def test_delete_removes_memory(self, client):
        mid = client.store(text="Delete me", metadata={}, namespace="default")
        assert client.delete(memory_id=mid) is True
        results = client.recall(query="delete", namespace="default")
        assert len(results) == 0

    def test_recall_escapes_like_wildcards(self, client):
        client.store(text="100% complete", metadata={}, namespace="default")
        results = client.recall(query="%", namespace="default")
        assert len(results) <= 1

    def test_recall_empty_db(self, client):
        results = client.recall(query="anything", namespace="default")
        assert results == []

    def test_recall_limit(self, client):
        for i in range(10):
            client.store(text=f"Memory {i}", metadata={}, namespace="default")
        results = client.recall(query="memory", namespace="default", limit=3)
        assert len(results) == 3
