"""Job base class — every built-in job extends this."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class JobContext:
    session_id: str = field(default_factory=lambda: f"job-{uuid.uuid4().hex[:8]}")
    config: dict[str, object] = field(default_factory=dict)


class Job(ABC):
    name: str

    @abstractmethod
    def run(self, context: JobContext) -> str:
        """Execute the job. Returns a human-readable result string."""
