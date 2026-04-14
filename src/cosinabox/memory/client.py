"""Memory service client — local SQLite or remote HTTP backend.

Local backend uses keyword search (LIKE %keyword%). Functional for
<10k memories. For semantic search, point MEMORY_SERVICE_URL at an
external memory service.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    namespace TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_ns ON memories (namespace);
"""


class MemoryClient(Protocol):
    def store(self, *, text: str, metadata: dict[str, Any], namespace: str) -> str: ...
    def recall(self, *, query: str, namespace: str, limit: int = 5) -> list[dict[str, Any]]: ...
    def search(self, *, query: str, namespace: str) -> list[dict[str, Any]]: ...
    def delete(self, *, memory_id: str) -> bool: ...


def _escape_like(query: str) -> str:
    """Escape LIKE wildcards so user input doesn't match everything."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class LocalMemoryClient:
    """SQLite-backed memory with keyword search.

    Good for <10k memories. For semantic search, use RemoteMemoryClient.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.db_path, check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_MEMORY_SCHEMA)
        self._conn.commit()

    def store(self, *, text: str, metadata: dict[str, Any], namespace: str) -> str:
        mid = uuid.uuid4().hex
        ts = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO memories (id, text, metadata_json, namespace, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (mid, text, json.dumps(metadata, default=str), namespace, ts),
        )
        self._conn.commit()
        return mid

    def recall(self, *, query: str, namespace: str, limit: int = 5) -> list[dict[str, Any]]:
        escaped = _escape_like(query)
        pattern = f"%{escaped}%"
        cur = self._conn.execute(
            "SELECT id, text, metadata_json, namespace, created_at "
            "FROM memories WHERE namespace = ? "
            "AND (text LIKE ? ESCAPE '\\' OR metadata_json LIKE ? ESCAPE '\\') "
            "ORDER BY created_at DESC LIMIT ?",
            (namespace, pattern, pattern, limit),
        )
        return [
            {
                "id": row["id"],
                "text": row["text"],
                "metadata": json.loads(row["metadata_json"]),
                "namespace": row["namespace"],
                "created_at": row["created_at"],
            }
            for row in cur.fetchall()
        ]

    def search(self, *, query: str, namespace: str) -> list[dict[str, Any]]:
        return self.recall(query=query, namespace=namespace, limit=50)

    def delete(self, *, memory_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


class RemoteMemoryClient:
    """HTTP client to an external memory service (e.g., Railway-hosted)."""

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        resp = httpx.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()

    def store(self, *, text: str, metadata: dict[str, Any], namespace: str) -> str:
        try:
            data = self._post("/memories", {
                "text": text, "metadata": metadata, "namespace": namespace,
            })
            return str(data.get("id", ""))
        except Exception:
            logger.warning("Memory service store failed", exc_info=True)
            return ""

    def recall(self, *, query: str, namespace: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            data = self._post("/recall", {
                "query": query, "namespace": namespace, "limit": limit,
            })
            return data if isinstance(data, list) else data.get("results", [])
        except Exception:
            logger.warning("Memory service recall failed", exc_info=True)
            return []

    def search(self, *, query: str, namespace: str) -> list[dict[str, Any]]:
        try:
            data = self._post("/search", {
                "query": query, "namespace": namespace,
            })
            return data if isinstance(data, list) else data.get("results", [])
        except Exception:
            logger.warning("Memory service search failed", exc_info=True)
            return []

    def delete(self, *, memory_id: str) -> bool:
        try:
            httpx.delete(
                f"{self.base_url}/memories/{memory_id}",
                headers=self._headers,
                timeout=5.0,
            )
            return True
        except Exception:
            logger.warning("Memory service delete failed", exc_info=True)
            return False


def resolve_memory_client(*, db_path: str | Path) -> LocalMemoryClient | RemoteMemoryClient:
    """Pick local or remote memory client based on env vars."""
    url = os.getenv("MEMORY_SERVICE_URL")
    if url:
        api_key = os.getenv("MEMORY_API_KEY", "")
        logger.info("Using remote memory service: %s", url)
        return RemoteMemoryClient(base_url=url, api_key=api_key)
    logger.info("Using local memory (SQLite keyword search)")
    return LocalMemoryClient(db_path=db_path)
