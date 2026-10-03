"""Shared graph state."""

from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """Partial graph update. ``spec`` is replaced wholesale; lists are not appended.

    Artifact flags live inside ``spec``, not as sibling keys.
    """

    spec: dict[str, Any]
    interrupt_kind: str
    validation_errors: list[str]
    session_dir: str
    planner_input_notes: list[str]
    agent_auto_replan_done: bool
    lab_up_detail: str


def dump_spec(spec: Any) -> dict[str, Any]:
    """JSON-mode dump so checkpoints store enum values, not enum classes."""
    if hasattr(spec, "model_dump"):
        data = spec.model_dump(mode="json")
        return data if isinstance(data, dict) else {}
    if isinstance(spec, dict):
        return spec
    return {}

