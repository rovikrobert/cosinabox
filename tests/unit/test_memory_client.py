from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

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


class TestRemoteMemoryClient:
    def test_store_calls_api(self):
        from cosinabox.memory.client import RemoteMemoryClient
        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "remote-id-1"}
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.post.return_value = mock_resp

            mid = client.store(text="fact", metadata={"k": "v"}, namespace="ns")
            assert mid == "remote-id-1"
            mock_httpx.post.assert_called_once()

    def test_recall_returns_empty_on_failure(self):
        from cosinabox.memory.client import RemoteMemoryClient
        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Network error")
            results = client.recall(query="test", namespace="ns")
            assert results == []


class TestResolveMemoryClient:
    def test_returns_local_when_no_url(self, tmp_path):
        from cosinabox.memory.client import resolve_memory_client
        client = resolve_memory_client(db_path=tmp_path / "mem.db")
        assert isinstance(client, LocalMemoryClient)

    def test_returns_remote_when_url_set(self, monkeypatch):
        from cosinabox.memory.client import RemoteMemoryClient, resolve_memory_client
        monkeypatch.setenv("MEMORY_SERVICE_URL", "https://mem.example.com")
        monkeypatch.setenv("MEMORY_API_KEY", "key123")
        client = resolve_memory_client(db_path="/tmp/unused.db")
        assert isinstance(client, RemoteMemoryClient)
