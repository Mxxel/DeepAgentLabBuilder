"""Interview ring: idea → ask_stop → choose_next_move / first-build / stale rebuild."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.graph.state import GraphState, dump_spec
from homelab_creator.graph.nodes import (
    ask_extra_paths,
    combined_form,
    compose_exists,
    extend_chain,
    lab_builder,
    lab_up,
    research_worker,
    vuln_planner,
    writeup_writer,
)
from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.validators import has_valid_path, is_plan_ready

IDEA_SUGGESTIONS = [
    "Small accounting firm with a public web app",
    "Regional clinic with EMR on an internal VLAN",
    "SaaS startup with a jump host and crown-jewel admin plane",
]


def _spec(state: GraphState) -> LabSpec:
    return LabSpec.model_validate(state.get("spec") or {})


def _allowed_moves(state: GraphState) -> list[str]:
    spec = _spec(state)
    allowed = ["more_brainstorm"]
    if spec.idea.strip() and not spec.form_completed:
        allowed.append("lock_idea_and_form")
    if spec.form_completed:
        allowed.append("redo_form")
    if is_plan_ready(spec) and has_valid_path(spec):
        allowed.append("ask_extra_paths")
    has_compose = compose_exists(state)
    if is_plan_ready(spec) and not has_compose:
        allowed.append("build")
    if has_compose:
        allowed.append("rebuild")
        allowed.append("lab_up")
    return allowed


def offer_idea(state: GraphState) -> Command[Literal["ask_stop"]]:
    """Interrupt for a company idea (free text or a suggestion index), then ``ask_stop``."""
    prompt = envelope(
        "offer_idea",
        suggestions=IDEA_SUGGESTIONS,
        allowed=["free_text", "pick"],
    )
    spec = _spec(state)
    while True:
        value = interrupt(prompt)
        if isinstance(value, dict) and "pick" in value:
            try:
                idx = int(value["pick"])
            except (TypeError, ValueError):
                prompt = envelope(
                    "offer_idea",
                    suggestions=IDEA_SUGGESTIONS,
                    allowed=["free_text", "pick"],
                    error="bad_pick",
                )
                continue
            if idx < 0 or idx >= len(IDEA_SUGGESTIONS):
                prompt = envelope(
                    "offer_idea",
                    suggestions=IDEA_SUGGESTIONS,
                    allowed=["free_text", "pick"],
                    error="bad_pick",
                )
                continue
            spec.idea = IDEA_SUGGESTIONS[idx]
            break
        if isinstance(value, dict) and "idea" in value:
            idea = str(value["idea"]).strip()
            if not idea:
                prompt = envelope(
                    "offer_idea",
                    suggestions=IDEA_SUGGESTIONS,
                    allowed=["free_text", "pick"],
                    error="empty_idea",
                )
                continue
            spec.idea = idea
            break
        if isinstance(value, str) and value.strip():
            spec.idea = value.strip()
            break
        prompt = envelope(
            "offer_idea",
            suggestions=IDEA_SUGGESTIONS,
            allowed=["free_text", "pick"],
            error="empty_idea",
        )
    spec.idea_locked = False
    return Command(update={"spec": dump_spec(spec), "interrupt_kind": "offer_idea"}, goto="ask_stop")


def ask_stop(state: GraphState) -> Command[Literal["after_stop", "__end__"]]:
    """Interrupt for continue or stop. Confirming stop is the only edge to END."""
    detail = str(state.get("lab_up_detail") or "")
    prompt = envelope("ask_stop", allowed=["continue", "stop"], **({"detail": detail} if detail else {}))
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in ("continue", "stop"):
            break
        prompt = envelope(
            "ask_stop",
            allowed=["continue", "stop"],
            error="unknown_action",
            **({"detail": detail} if detail else {}),
        )
    if action == "stop":
        return Command(update={"lab_up_detail": ""}, goto=END)
    return Command(update={"lab_up_detail": ""}, goto="after_stop")


def after_stop(state: GraphState) -> Command[Literal["lab_builder", "choose_next_move"]]:
    """After continue: first-build or stale rebuild when plan-ready, else the move menu."""
    spec = _spec(state)
    if is_plan_ready(spec) and not compose_exists(state):
        return Command(goto="lab_builder")
    if is_plan_ready(spec) and spec.artifacts_stale:
        return Command(goto="lab_builder")
    return Command(goto="choose_next_move")


def choose_next_move(state: GraphState) -> Command:
    """Interrupt with the currently allowed actions and dispatch that choice immediately."""
    spec = _spec(state)
    allowed = _allowed_moves(state)
    prompt = envelope("choose_next_move", allowed=allowed)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in allowed:
            break
        prompt = envelope("choose_next_move", allowed=allowed, error="unknown_action")
    updates: dict[str, Any] = {"interrupt_kind": "choose_next_move"}
    dest = "ask_stop"
    if action == "more_brainstorm":
        spec.idea_locked = False
        dest = "offer_idea"
    elif action == "lock_idea_and_form":
        spec.idea_locked = True
        dest = "combined_form"
    elif action == "redo_form":
        spec.idea_locked = True
        if compose_exists(state):
            spec.artifacts_stale = True
        dest = "combined_form"
    elif action == "ask_extra_paths":
        dest = "ask_extra_paths"
    elif action in ("build", "rebuild"):
        dest = "lab_builder"
    elif action == "lab_up":
        dest = "lab_up"
    updates["spec"] = dump_spec(spec)
    return Command(update=updates, goto=dest)


def compile_graph(checkpointer: Any | None = None, *, persist_path: Path | None = None):
    """Compile the interview graph.

    ``checkpointer`` wins when given. Otherwise ``persist_path`` opens SQLite,
    and a missing path uses an in-memory saver (tests).
    """
    if checkpointer is not None:
        saver = checkpointer
    elif persist_path is not None:
        from homelab_creator.graph.checkpoint import sqlite_saver

        saver = sqlite_saver(persist_path)
    else:
        from homelab_creator.graph.checkpoint import checkpoint_serde

        saver = InMemorySaver(serde=checkpoint_serde())
    builder = StateGraph(GraphState)
    builder.add_node("offer_idea", offer_idea)
    builder.add_node("ask_stop", ask_stop)
    builder.add_node("after_stop", after_stop)
    builder.add_node("choose_next_move", choose_next_move)
    builder.add_node("combined_form", combined_form)
    builder.add_node("research_worker", research_worker)
    builder.add_node("vuln_planner", vuln_planner)
    builder.add_node("extend_chain", extend_chain)
    builder.add_node("ask_extra_paths", ask_extra_paths)
    builder.add_node("lab_builder", lab_builder)
    builder.add_node("writeup_writer", writeup_writer)
    builder.add_node("lab_up", lab_up)
    builder.add_edge(START, "offer_idea")
    return builder.compile(checkpointer=saver)
