"""Sub-agent — isolated agent with its own memory namespace and prompt."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_AGENTS: dict[str, "SubAgent"] = {}


class _NamespacedMemoryClient:
    """Wrapper that forces a namespace on all memory operations."""

    def __init__(self, inner: Any, namespace: str) -> None:
        self._inner = inner
        self._namespace = namespace

    def store(self, *, text: str, metadata: dict[str, Any], namespace: str = "") -> str:
        return self._inner.store(text=text, metadata=metadata, namespace=self._namespace)

    def recall(self, *, query: str, namespace: str = "", limit: int = 5) -> list[dict[str, Any]]:
        return self._inner.recall(query=query, namespace=self._namespace, limit=limit)

    def search(self, *, query: str, namespace: str = "") -> list[dict[str, Any]]:
        return self._inner.search(query=query, namespace=self._namespace)

    def delete(self, *, memory_id: str) -> bool:
        return self._inner.delete(memory_id=memory_id)


DEFAULT_MAX_CONCURRENT_INGESTS = 3


class SubAgent:
    def __init__(
        self,
        *,
        name: str,
        namespace: str,
        system_prompt: str,
        agent_loop: Any,
        memory_client: Any,
        allowed_tools: list[str] | None = None,
        max_concurrent_ingests: int = DEFAULT_MAX_CONCURRENT_INGESTS,
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.system_prompt = system_prompt
        self._loop = agent_loop
        self._namespaced_client = _NamespacedMemoryClient(memory_client, namespace)
        # Default [] = no external tools. Sub-agents should opt-in explicitly
        # rather than inherit the full parent registry (which could include
        # write tools like gmail_send that a read-only sub-agent must not reach).
        self.allowed_tools: list[str] = [] if allowed_tools is None else list(allowed_tools)
        # Bounded fan-out: ingest() spawns daemon threads that each run a full
        # AgentLoop (Sonnet + writes to shared SQLite). Without a bound, a
        # 100-stakeholder scan could spawn 100 concurrent Sonnet calls. The
        # semaphore caps live workers; extra ingest() calls queue behind it on
        # their own thread until a slot is free.
        if max_concurrent_ingests < 1:
            raise ValueError("max_concurrent_ingests must be >= 1")
        self.max_concurrent_ingests = max_concurrent_ingests
        self._ingest_sem = threading.Semaphore(max_concurrent_ingests)

    def ingest(self, content: str) -> None:
        """Fire-and-forget: process content in a background thread.

        Concurrency is bounded by ``self._ingest_sem`` — if ``max_concurrent_ingests``
        workers are already running, newly-spawned threads block on acquire()
        until a slot frees up.
        """
        def _run() -> None:
            with self._ingest_sem:
                try:
                    session = f"{self.name}-ingest-{uuid.uuid4().hex}"
                    self._loop.run(
                        prompt=content, session_id=session,
                        system_prompt_override=self.system_prompt,
                        allowed_tools=self.allowed_tools,
                    )
                except Exception:
                    logger.warning("SubAgent %s ingest failed", self.name, exc_info=True)
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def query(self, question: str) -> str:
        """Synchronous query — blocks until response is ready."""
        session = f"{self.name}-query-{uuid.uuid4().hex}"
        result = self._loop.run(
            prompt=question, session_id=session,
            system_prompt_override=self.system_prompt,
            allowed_tools=self.allowed_tools,
        )
        return result.final_text or "(no response)"


def register_agent(agent: SubAgent) -> None:
    _AGENTS[agent.name] = agent


def get_agent(name: str) -> SubAgent | None:
    return _AGENTS.get(name)
