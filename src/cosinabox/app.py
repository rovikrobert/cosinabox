"""Top-level App entry point. Filled in during M2."""

from __future__ import annotations


class App:
    """Compose personality + stakeholders + jobs and run the bot + scheduler."""

    def __init__(self, config_dir: str | None = None) -> None:
        self.config_dir = config_dir

    def run(self) -> None:
        raise NotImplementedError("App.run lands in Plan 1 Milestone 2")
