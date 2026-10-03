"""Headless TUI: scripted show(payload) -> resume_value."""

from __future__ import annotations

from typing import Any

PAUSE = object()


class ScriptedTUI:
    """Replay a list of resume values. Used by tests and headless scripts."""

    def __init__(
        self,
        answers: list[Any],
        *,
        auto_approve_writes: bool = True,
        auto_approve_compose: bool = True,
        pause_when_exhausted: bool = False,
    ) -> None:
        self.answers = list(answers)
        self.shown: list[dict[str, Any]] = []
        self.auto_approve_writes = auto_approve_writes
        self.auto_approve_compose = auto_approve_compose
        self.pause_when_exhausted = pause_when_exhausted
        self.paused = False
        self.progress_lines: list[str] = []

    def progress(self, message: str) -> None:
        self.progress_lines.append(str(message))

    def show(self, payload: dict[str, Any], *, hosts: list[dict] | None = None) -> Any:
        self.shown.append(payload)
        kind = payload.get("interrupt_kind")
        tool = payload.get("tool")
        if kind == "hitl_tool" and tool == "write_session_files" and self.auto_approve_writes:
            return "approve"
        if kind == "hitl_tool" and tool == "compose_cli" and self.auto_approve_compose:
            return "approve"
        if not self.answers:
            if self.pause_when_exhausted:
                self.paused = True
                return PAUSE
            raise RuntimeError(f"script exhausted at {kind}")
        return self.answers.pop(0)
