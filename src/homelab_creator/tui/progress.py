"""Stream lab-creation progress so the TUI is not silent between interrupts."""

from __future__ import annotations

from typing import Any

NODE_OVERVIEW = {
    "offer_idea": "Brainstorming the company idea. Next: continue or stop.",
    "ask_stop": "Decide whether to keep going or stop the session.",
    "choose_next_move": "Pick the next interview action (form, build, lab up, …).",
    "combined_form": "Recording vuln mode, difficulty, and research opt-in.",
    "research_worker": "Research: Tavily (if keyed) then notes. Next: planner fills the lab.",
    "vuln_planner": "Planner: catalog hosts, issues, and the compromise path. Next: extra paths or extend chain.",
    "extend_chain": "Plan is not ready. Extend hops, replan, or abandon generation.",
    "ask_extra_paths": "Optional extra compromise paths. Next: continue can build the lab.",
    "lab_builder": "Lab builder: compose + topology via file HITL. Next: writeup.",
    "writeup_writer": "Writeup: assessment inventory (no exploit recipes). Next: start or skip the lab.",
    "lab_up": "Lab up: compose up/skip/down for the isolated project.",
}


def emit(message: str) -> None:
    """Push a progress line on the LangGraph custom stream. Silent outside a run."""
    text = str(message).strip()
    if not text:
        return
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()({"progress": text})
    except Exception:
        return


def snapshot(spec: object) -> str:
    """One-line idea, form, host, and research-note counts from a spec dict."""
    if not isinstance(spec, dict):
        return ""
    idea = str(spec.get("idea") or "(none)")[:60]
    hosts = spec.get("hosts") if isinstance(spec.get("hosts"), list) else []
    research = spec.get("research") if isinstance(spec.get("research"), dict) else {}
    notes = research.get("notes") if isinstance(research.get("notes"), list) else []
    form = "yes" if spec.get("form_completed") else "no"
    return f"idea={idea} | form={form} | hosts={len(hosts)} | research_notes={len(notes)}"


def overview_for_node(name: str, update: object | None = None) -> str:
    """Operator-facing line for a graph node update, plus a spec snapshot when present."""
    headline = NODE_OVERVIEW.get(name, f"Working: {name}")
    spec = None
    if isinstance(update, dict):
        spec = update.get("spec")
    snap = snapshot(spec)
    if snap:
        return f"{headline}\n  {snap}"
    return headline


def custom_message(data: Any) -> str | None:
    """Text from a custom stream event, or None when the event has no progress string."""
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(data, dict):
        raw = data.get("progress") or data.get("message")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None
