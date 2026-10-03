"""Research worker: HITL search, notes + citations, no exploit recipes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.safety import contains_poc
from homelab_creator.tools.search import MissingSearchKeyError, SearchDisabledError, default_search
from homelab_creator.workers.agents import gather_notes_with_agent
from homelab_creator.workers.invoke import WorkerBudgetError
from homelab_creator.workers.llm import live_llm_enabled

SearchFn = Callable[[str], list[dict[str, Any]]]
RESEARCH_MAX_HITS = 16
RESEARCH_MAX_LEN = 500


def _hits_to_notes(hits: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    citations: list[str] = []
    for hit in hits[:RESEARCH_MAX_HITS]:
        snippet = str(hit.get("snippet") or hit.get("note") or "").strip()[:RESEARCH_MAX_LEN]
        url = str(hit.get("url") or hit.get("citation") or "").strip()[:RESEARCH_MAX_LEN]
        title = str(hit.get("title") or "").strip()[:RESEARCH_MAX_LEN]
        blob = f"{title} {snippet} {url}"
        if contains_poc(blob):
            continue
        if snippet:
            notes.append(snippet)
        elif title:
            notes.append(title)
        if url:
            citations.append(url)
    return notes, citations


def _hitl_retry_skip(query: str, error: str, detail: str = "") -> str:
    prompt = envelope(
        "hitl_tool",
        tool="search",
        args={"query": query},
        allowed=["retry", "skip"],
        error=error,
        detail=detail,
    )
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in ("retry", "skip"):
            return action
        prompt = envelope(
            "hitl_tool",
            tool="search",
            args={"query": query},
            allowed=["retry", "skip"],
            error="unknown_action",
        )


def _decide_search(query: str) -> str | None:
    prompt = envelope(
        "hitl_tool",
        tool="search",
        args={"query": query},
        allowed_decisions=["approve", "edit", "reject"],
        allowed=["approve", "edit", "reject"],
    )
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action == "reject":
            return None
        if action == "approve":
            return query
        if action == "edit":
            args = value.get("args") if isinstance(value, dict) else None
            if isinstance(args, dict) and str(args.get("query") or "").strip():
                return str(args["query"]).strip()
            prompt = envelope(
                "hitl_tool",
                tool="search",
                args={"query": query},
                allowed_decisions=["approve", "edit", "reject"],
                allowed=["approve", "edit", "reject"],
                error="empty_query",
            )
            continue
        prompt = envelope(
            "hitl_tool",
            tool="search",
            args={"query": query},
            allowed_decisions=["approve", "edit", "reject"],
            allowed=["approve", "edit", "reject"],
            error="unknown_action",
        )


def _empty_research(spec: LabSpec) -> LabSpec:
    current = spec.model_copy(deep=True)
    current.research.notes = []
    current.research.citations = []
    return current


def run_research(spec: LabSpec, *, search: SearchFn | None = None) -> LabSpec:
    """Approve a public-writeup query, then store notes and citation URLs.

    Opted-out specs clear notes and citations. ``search`` replaces Tavily in tests.
    Citations come from search URLs only; a missing key never invents them.
    """
    current = spec.model_copy(deep=True)
    if not current.research.opted_in:
        return _empty_research(current)
    query = f"public pentest bug bounty {current.idea}".strip()
    decided = _decide_search(query)
    if decided is None:
        return _empty_research(current)
    from homelab_creator.tui.progress import emit

    emit("Research: query approved. Searching with Tavily if a key is set.")
    backend = search if search is not None else default_search
    if not callable(backend):
        if _hitl_retry_skip(decided, "search_failed", "search is not callable") == "skip":
            return _empty_research(current)
        raise TypeError("search is not callable")
    while True:
        try:
            hits = backend(decided)
        except (MissingSearchKeyError, SearchDisabledError) as exc:
            if live_llm_enabled():
                emit("Research: Tavily unavailable — airouter notes only (citations stay empty).")
                return gather_notes_with_agent(current, decided)
            error = "missing_key" if isinstance(exc, MissingSearchKeyError) else "search_disabled"
            if _hitl_retry_skip(decided, error, str(exc)) == "skip":
                return _empty_research(current)
            continue
        except WorkerBudgetError:
            raise
        except Exception:
            if _hitl_retry_skip(decided, "search_failed", "search_failed") == "skip":
                return _empty_research(current)
            continue
        if not isinstance(hits, list):
            if _hitl_retry_skip(decided, "search_failed", "search must return a list") == "skip":
                return _empty_research(current)
            continue
        notes, citations = _hits_to_notes(hits)
        current.research.notes = notes
        current.research.citations = citations
        emit(f"Research: {len(notes)} notes, {len(citations)} citations. Using Tavily results (no extra model refine).")
        return current
