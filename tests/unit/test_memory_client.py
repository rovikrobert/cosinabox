from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cosinabox.memory.client import LocalMemoryClient


@pytest.fixture
def client(tmp_path):
    return LocalMemoryClient(db_path=tmp_path / "mem.db")


class TestLocalMemoryClient:
    def test_store_returns_id(self, client):
        mid = client.store(
            text="Decision: launch in Q3",
            metadata={"source": "meeting"},
            namespace="default",
        )
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

    def test_recall_raises_on_failure(self):
        """Regression guard: recall() must raise on network failure rather
        than returning []. Silent [] previously caused callers to treat a
        service outage as 'no memories exist'."""
        from cosinabox.memory.client import MemoryServiceError, RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Network error")
            with pytest.raises(MemoryServiceError):
                client.recall(query="test", namespace="ns")

    def test_store_raises_on_503(self):
        import httpx as real_httpx  # noqa: F401

        from cosinabox.memory.client import MemoryServiceError, RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
            mock_httpx.post.return_value = mock_resp
            with pytest.raises(MemoryServiceError):
                client.store(text="fact", metadata={}, namespace="ns")

    def test_search_raises_on_failure(self):
        from cosinabox.memory.client import MemoryServiceError, RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Network error")
            with pytest.raises(MemoryServiceError):
                client.search(query="test", namespace="ns")

    def test_delete_returns_false_on_404(self):
        """delete() must check HTTP status and return False on error responses."""
        from cosinabox.memory.client import RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.is_success = False
            mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
            mock_httpx.delete.return_value = mock_resp
            assert client.delete(memory_id="nonexistent") is False

    def test_delete_returns_false_on_500(self):
        """delete() must return False when the API returns a server error."""
        from cosinabox.memory.client import RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.is_success = False
            mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
            mock_httpx.delete.return_value = mock_resp
            assert client.delete(memory_id="err") is False

    def test_delete_returns_true_on_success(self):
        """delete() must return True only when the API returns 2xx."""
        from cosinabox.memory.client import RemoteMemoryClient

        client = RemoteMemoryClient(base_url="https://mem.example.com", api_key="key123")
        with patch("cosinabox.memory.client.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.is_success = True
            mock_resp.raise_for_status = MagicMock()  # no exception
            mock_httpx.delete.return_value = mock_resp
            assert client.delete(memory_id="valid-id") is True


class TestResolveMemoryClient:
    def test_returns_local_when_no_url(self, tmp_path, monkeypatch):
        from cosinabox.memory.client import resolve_memory_client

        monkeypatch.delenv("MEMORY_SERVICE_URL", raising=False)
        client = resolve_memory_client(db_path=tmp_path / "mem.db")
        assert isinstance(client, LocalMemoryClient)

    def test_returns_remote_when_url_set(self, monkeypatch):
        from cosinabox.memory.client import RemoteMemoryClient, resolve_memory_client

        monkeypatch.setenv("MEMORY_SERVICE_URL", "https://mem.example.com")
        monkeypatch.setenv("MEMORY_API_KEY", "key123")
        client = resolve_memory_client(db_path="/tmp/unused.db")
        assert isinstance(client, RemoteMemoryClient)

    def test_missing_api_key_raises(self, monkeypatch):
        """If the user sets MEMORY_SERVICE_URL but forgets MEMORY_API_KEY,
        fail at startup rather than silently dropping every memory."""
        from cosinabox.memory.client import resolve_memory_client

        monkeypatch.setenv("MEMORY_SERVICE_URL", "https://mem.example.com")
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
        with pytest.raises(ValueError, match="MEMORY_API_KEY"):
            resolve_memory_client(db_path="/tmp/unused.db")
