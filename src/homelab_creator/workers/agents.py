"""Deep Agent factories. Parent graph still owns HITL via interrupt()."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import ValidationError

from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.safety import contains_poc
from homelab_creator.workers.llm import chat_model, live_llm_enabled
from homelab_creator.workers.invoke import WorkerBudgetError
from homelab_creator.tui.progress import emit

PLANNER_PROMPT = """You are the vuln planner worker for an isolated assessment homelab.
Objective is always full company compromise (pwn the company).
Use catalog roles only: foothold, internal, crown_jewel, workstation, mail, jump.
Invent assessment-style finding classes, not exploit recipes or PoCs.
If research notes are present, map them to vuln classes before inventing leftovers.
Call commit_plan with the filled spec JSON after applying catalog minima.
"""

RESEARCH_PROMPT = """You turn public pentest/bug-bounty snippets into assessment notes.
Drop exploit recipes. Keep citations as URLs only.
"""


def create_planner_agent(*, model: Any | None = None, on_commit=None):
    """Deep Agent that commits a catalog-only ``LabSpec``. The parent graph still routes."""
    from deepagents import create_deep_agent

    llm = model if model is not None else chat_model()

    @tool
    def commit_plan(spec_json: str) -> str:
        """Record a catalog-only LabSpec JSON (no exploit recipes)."""
        if contains_poc(spec_json):
            return "rejected: exploit language"
        parsed = LabSpec.model_validate_json(spec_json)
        if on_commit is not None:
            on_commit(parsed)
        return "ok"

    return create_deep_agent(
        model=llm,
        tools=[commit_plan],
        system_prompt=PLANNER_PROMPT,
        name="vuln-planner",
    )


def create_research_agent(*, model: Any | None = None, on_commit=None):
    """Deep Agent that commits assessment notes. Citation URLs are not invented here."""
    from deepagents import create_deep_agent

    llm = model if model is not None else chat_model()

    @tool
    def commit_notes(notes: list[str], citations: list[str]) -> str:
        """Store assessment notes and URL citations (no exploit recipes)."""
        if not isinstance(notes, list) or not isinstance(citations, list):
            return "rejected: lists required"
        cleaned_notes = [str(n).strip()[:500] for n in notes if str(n).strip() and not contains_poc(str(n))]
        cleaned_cites = [str(c).strip()[:500] for c in citations if str(c).strip() and not contains_poc(str(c))]
        if on_commit is not None:
            on_commit(cleaned_notes, cleaned_cites)
        return "ok"

    return create_deep_agent(
        model=llm,
        tools=[commit_notes],
        system_prompt=RESEARCH_PROMPT,
        name="research-worker",
    )


def _run_agent(agent: Any, payload: str, *, keep_message: str) -> bool:
    """Return True if invoke finished. Timeouts keep caller state."""
    try:
        agent.invoke({"messages": [{"role": "user", "content": payload}]})
    except WorkerBudgetError:
        raise
    except Exception as exc:
        emit(f"{keep_message} ({type(exc).__name__})")
        return False
    return True


def gather_notes_with_agent(spec: LabSpec, query: str) -> LabSpec:
    """Model-sourced notes when web search has no key. Never invent citation URLs."""
    if not live_llm_enabled():
        current = spec.model_copy(deep=True)
        current.research.notes = []
        current.research.citations = []
        return current
    committed: dict[str, tuple[list[str], list[str]]] = {}

    def on_commit(notes: list[str], citations: list[str]) -> None:
        committed["pair"] = (notes, [])

    payload = (
        f"Idea: {spec.idea or 'company lab'}\n"
        f"Approved query: {query}\n"
        "Web search is unavailable. Call commit_notes with well-known public "
        "pentest/bug-bounty finding classes only. citations must be []. "
        "Do not invent URLs. No exploit recipes."
    )
    emit("Research agent: model-sourced finding classes (no invented URLs).")
    try:
        agent = create_research_agent(on_commit=on_commit)
    except Exception as exc:
        emit(f"Research: could not start model ({type(exc).__name__}).")
        current = spec.model_copy(deep=True)
        current.research.notes = []
        current.research.citations = []
        return current
    if not _run_agent(agent, payload, keep_message="Research: model timed out or failed; no notes"):
        current = spec.model_copy(deep=True)
        current.research.notes = []
        current.research.citations = []
        return current
    current = spec.model_copy(deep=True)
    if "pair" in committed:
        current.research.notes, current.research.citations = committed["pair"]
    else:
        current.research.notes = []
        current.research.citations = []
    return current


def refine_notes_with_agent(spec: LabSpec) -> LabSpec:
    """Live research pass after HITL search. Failures keep heuristic notes."""
    if not live_llm_enabled():
        return spec
    committed: dict[str, tuple[list[str], list[str]]] = {}

    def on_commit(notes: list[str], citations: list[str]) -> None:
        committed["pair"] = (notes, citations)

    payload = (
        f"Idea: {spec.idea or 'company lab'}\n"
        f"Notes:\n" + "\n".join(spec.research.notes) + "\n"
        f"Citations:\n" + "\n".join(spec.research.citations) + "\n"
        "Call commit_notes with assessment-style classes only. No exploit recipes."
    )
    emit("Research: optional model refine of Tavily notes (can take a while).")
    try:
        agent = create_research_agent(on_commit=on_commit)
    except Exception as exc:
        emit(f"Research: refine skipped ({type(exc).__name__}); keeping search notes.")
        return spec
    if not _run_agent(agent, payload, keep_message="Research: refine timed out; keeping Tavily notes"):
        return spec
    if "pair" not in committed:
        return spec
    current = spec.model_copy(deep=True)
    current.research.notes, current.research.citations = committed["pair"]
    return current


def refine_plan_with_agent(spec: LabSpec) -> LabSpec:
    """Live planner. On API/validation failure, keep the heuristic spec."""
    if not live_llm_enabled():
        return spec
    committed: dict[str, LabSpec] = {}

    def on_commit(parsed: LabSpec) -> None:
        committed["spec"] = parsed

    idea = spec.idea or "company lab"
    notes = "\n".join(spec.research.notes) if spec.research.opted_in else ""
    payload = (
        f"Idea: {idea}\nDifficulty: {spec.difficulty.value}\nMode: {spec.vuln_mode}\n"
        f"Research notes:\n{notes or '(none)'}\n"
        f"Current spec JSON:\n{spec.model_dump_json()}\n"
        "Call commit_plan with catalog-only JSON. Keep user vulns. No PoCs."
    )
    try:
        agent = create_planner_agent(on_commit=on_commit)
    except Exception as exc:
        emit(f"Planner: model unavailable ({type(exc).__name__}); keeping catalog fill.")
        return spec
    if not _run_agent(agent, payload, keep_message="Planner: airouter timed out; keeping catalog fill"):
        return spec
    return committed.get("spec", spec)
