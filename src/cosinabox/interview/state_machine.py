"""Interview state machine — owns the 10-step interview."""

from __future__ import annotations

import json
from pathlib import Path

from cosinabox.interview.steps import STEPS

STATE_FILENAME = ".cosinabox/interview-state.json"


class InterviewMachine:
    def __init__(self, *, config_dir: Path) -> None:
        self.config_dir = Path(config_dir)
        self.current_step_index = 0
        self._completed = False

    def start(self) -> None:
        self.current_step_index = 0
        self._completed = False
        (self.config_dir / ".cosinabox").mkdir(parents=True, exist_ok=True)
        self._persist()

    def next_question(self) -> str:
        if self.is_complete():
            return "INTERVIEW COMPLETE"
        return STEPS[self.current_step_index].prompt()

    def answer(self, text: str) -> None:
        if self.is_complete():
            return
        STEPS[self.current_step_index].apply(text, self.config_dir)
        self.current_step_index += 1
        if self.current_step_index >= len(STEPS):
            self._completed = True
        self._persist()

    def is_complete(self) -> bool:
        return self._completed

    def _persist(self) -> None:
        path = self.config_dir / STATE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"index": self.current_step_index, "complete": self._completed}))

    @classmethod
    def resume(cls, *, config_dir: Path) -> InterviewMachine:
        m = cls(config_dir=config_dir)
        path = config_dir / STATE_FILENAME
        if path.exists():
            state = json.loads(path.read_text())
            m.current_step_index = state["index"]
            m._completed = state["complete"]
        return m
