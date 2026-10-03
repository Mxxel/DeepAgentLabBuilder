"""JSON-serializable interrupt payloads."""

from __future__ import annotations

from typing import Any


def envelope(kind: str, **fields: Any) -> dict[str, Any]:
    """Interrupt payload. ``interrupt_kind`` is always present so the TUI has one switch."""
    payload = {"interrupt_kind": kind, **fields}
    return payload


def resume_action(value: Any) -> str:
    """Action id from a string resume or from ``action`` / ``type`` on a dict resume."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("action") or value.get("type") or "")
    return ""
