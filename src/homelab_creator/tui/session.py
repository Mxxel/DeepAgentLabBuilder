"""Drive a compiled graph with a TUI adapter: show(payload) -> resume."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.tui.headless import PAUSE
from homelab_creator.tui.progress import custom_message, overview_for_node


class TUI(Protocol):
    """Adapter contract: show one interrupt payload and return the resume value."""

    def show(self, payload: dict[str, Any], *, hosts: list[dict] | None = None) -> Any:
        """Render ``payload`` and return the value passed to ``Command(resume=...)``."""
        ...


def _payload_from_snap(compiled, cfg) -> dict[str, Any]:
    snap = compiled.get_state(cfg)
    interrupts = list(getattr(snap, "interrupts", None) or ())
    if not interrupts:
        return dict(snap.values or {})
    return {"__interrupt__": interrupts}


def _notify(tui: TUI | None, message: str) -> None:
    if tui is None or not message:
        return
    progress = getattr(tui, "progress", None)
    if callable(progress):
        progress(message)


def _advance(compiled, payload: Any, cfg, tui: TUI | None = None) -> dict[str, Any]:
    try:
        for item in compiled.stream(payload, cfg, stream_mode=["updates", "custom"]):
            if isinstance(item, tuple) and len(item) == 3:
                _ns, mode, data = item
            elif isinstance(item, tuple) and len(item) == 2:
                mode, data = item
            else:
                mode, data = "updates", item
            if mode == "custom":
                msg = custom_message(data)
                if msg:
                    _notify(tui, msg)
            elif mode == "updates" and isinstance(data, dict):
                for name, update in data.items():
                    _notify(tui, overview_for_node(str(name), update))
    except Exception as exc:
        # Last resort: keep checkpointed interrupt state instead of exiting the CLI.
        _notify(tui, f"Step failed ({type(exc).__name__}): {exc}. Resume from checkpoint if a prompt reappears.")
    return _payload_from_snap(compiled, cfg)


def _payload(result: dict) -> dict[str, Any]:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return {}
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {}


def run_session(
    tui: TUI,
    *,
    session_dir: Path,
    thread_id: str,
    graph: Any | None = None,
    configurable: dict[str, Any] | None = None,
    persist_path: Path | None = None,
) -> dict[str, Any]:
    """Stream the graph until the TUI returns ``PAUSE`` or the thread has no interrupt.

    A checkpointed interrupt for ``thread_id`` is shown again instead of restarting the idea.
    """
    compiled = graph or compile_graph(persist_path=persist_path)
    extra = dict(configurable or {})
    cfg = {"configurable": {"thread_id": thread_id, **extra}}
    snap = compiled.get_state(cfg)
    pending = getattr(snap, "interrupts", None) or ()
    if pending:
        result: dict[str, Any] = {"__interrupt__": list(pending)}
    elif snap.values.get("session_dir"):
        result = _advance(compiled, None, cfg, tui)
    else:
        result = _advance(compiled, {"spec": {}, "session_dir": str(session_dir)}, cfg, tui)
    while result.get("__interrupt__"):
        payload = _payload(result)
        spec = compiled.get_state(cfg).values.get("spec") or {}
        hosts = spec.get("hosts") if isinstance(spec, dict) else None
        resume = tui.show(payload, hosts=hosts if isinstance(hosts, list) else None)
        if resume is PAUSE:
            break
        result = _advance(compiled, Command(resume=resume), cfg, tui)
    return result
