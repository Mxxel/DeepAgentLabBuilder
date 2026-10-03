"""Worker invoke wrapper: budget and transient failures stay in the batch."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.tui.progress import emit

T = TypeVar("T")


class WorkerBudgetError(Exception):
    """Raised when a worker hits recursion/tool budget."""


class WorkerOutcome(str, Enum):
    skip = "skip"
    ask_stop = "ask_stop"


def _hitl_worker_failure(error: str, detail: str) -> str:
    emit(f"Worker issue: {error} — {detail[:200]}")
    payload = envelope(
        "worker_budget",
        allowed=["retry", "skip", "ask_stop"],
        error=error,
        detail=detail[:500],
    )
    while True:
        value = interrupt(payload)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in ("retry", "skip", "ask_stop"):
            return action
        payload = envelope(
            "worker_budget",
            allowed=["retry", "skip", "ask_stop"],
            error="unknown_action",
        )


def invoke_worker(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T | WorkerOutcome:
    """Run a worker. Never let LLM/network crashes kill the interview.

    ``GraphBubbleUp`` (HITL ``interrupt()``) always propagates.
    Budget and other failures share retry / skip / ask_stop.
    """
    while True:
        try:
            return fn(*args, **kwargs)
        except GraphBubbleUp:
            raise
        except WorkerBudgetError as exc:
            action = _hitl_worker_failure("budget", str(exc) or "budget")
        except Exception as exc:
            name = type(exc).__name__
            error = "timeout" if "Timeout" in name or "timeout" in str(exc).lower() else "worker_failed"
            action = _hitl_worker_failure(error, f"{name}: {exc}")
        if action == "retry":
            emit("Retrying worker…")
            continue
        if action == "skip":
            return WorkerOutcome.skip
        return WorkerOutcome.ask_stop


def unwrap_worker(result: T | WorkerOutcome, fallback: T) -> tuple[T, WorkerOutcome | None]:
    """Split a worker return into a value and an optional skip or ask-stop outcome.

    Skip and ask-stop keep ``fallback`` (usually the spec from before the call).
    """
    if result is WorkerOutcome.skip:
        return fallback, WorkerOutcome.skip
    if result is WorkerOutcome.ask_stop:
        return fallback, WorkerOutcome.ask_stop
    return result, None
