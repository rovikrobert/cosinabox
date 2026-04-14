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

    def ingest(self, content: str) -> None:
        """Fire-and-forget: process content in a background thread."""
        def _run() -> None:
            try:
                session = f"{self.name}-ingest-{uuid.uuid4().hex[:8]}"
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
        session = f"{self.name}-query-{uuid.uuid4().hex[:8]}"
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
