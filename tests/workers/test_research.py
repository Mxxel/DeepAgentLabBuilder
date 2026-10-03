from pathlib import Path

from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import LabSpec
from homelab_creator.tools.search import MissingSearchKeyError, SearchDisabledError
from homelab_creator.workers.invoke import WorkerBudgetError
from homelab_creator.workers.research import run_research
from tests.spec.factories import STUB_CITATION, STUB_NOTE


def _kind(result) -> str:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return ""
    first = interrupts[0]
    value = getattr(first, "value", first)
    if isinstance(value, dict):
        return str(value.get("interrupt_kind") or "")
    return ""


def _payload(result) -> dict:
    interrupts = result.get("__interrupt__") or []
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {}


def _lock_research(graph, cfg, tmp_path: Path):
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    return graph.invoke(
        Command(
            resume={
                "action": "submit",
                "vuln_mode": "agent",
                "difficulty": "beginner",
                "research.opted_in": True,
            }
        ),
        cfg,
    )


def test_opted_out_does_not_call_search():
    calls: list[str] = []

    def search(query: str):
        calls.append(query)
        return []

    spec = LabSpec(research={"opted_in": False})
    out = run_research(spec, search=search)
    assert calls == []
    assert out.research.notes == []
    assert out.research.citations == []


def test_fake_search_fills_schema(tmp_path: Path):
    def search(query: str):
        return [{"title": "Edge", "url": STUB_CITATION, "snippet": STUB_NOTE}]

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "search-ok", "search": search}}
    r = _lock_research(graph, cfg, tmp_path)
    assert _kind(r) == "hitl_tool"
    assert _payload(r).get("tool") == "search"
    assert "approve" in (_payload(r).get("allowed_decisions") or [])
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _kind(r) == "ask_extra_paths"
    spec = graph.get_state(cfg).values["spec"]
    assert STUB_NOTE in spec["research"]["notes"]
    assert STUB_CITATION in spec["research"]["citations"]


def test_hitl_reject_does_not_call_search(tmp_path: Path):
    calls: list[str] = []

    def search(query: str):
        calls.append(query)
        return [{"title": "x", "url": "https://example.invalid/x", "snippet": "x"}]

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "reject", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    graph.invoke(Command(resume="reject"), cfg)
    assert calls == []
    spec = graph.get_state(cfg).values["spec"]
    assert spec["research"]["citations"] == []


def test_poc_hits_are_dropped(tmp_path: Path):
    def search(query: str):
        return [{"title": "bad", "url": "https://example.invalid/exploit-poc", "snippet": "clean text"}]

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "poc", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    graph.invoke(Command(resume="approve"), cfg)
    spec = graph.get_state(cfg).values["spec"]
    assert spec["research"]["notes"] == []
    assert spec["research"]["citations"] == []


def test_no_search_key_uses_model_notes(monkeypatch, tmp_path: Path):
    from homelab_creator.spec.models import LabSpec

    monkeypatch.setattr("homelab_creator.workers.research.live_llm_enabled", lambda: True)

    def fake_gather(spec: LabSpec, query: str) -> LabSpec:
        current = spec.model_copy(deep=True)
        current.research.notes = ["legacy auth on vpn"]
        current.research.citations = []
        assert "pentest" in query or query
        return current

    monkeypatch.setattr("homelab_creator.workers.research.gather_notes_with_agent", fake_gather)
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "model-research"}}
    r = _lock_research(graph, cfg, tmp_path)
    assert _kind(r) == "hitl_tool"
    assert _payload(r).get("error") in (None, "")
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _payload(r).get("error") != "missing_key"
    spec = graph.get_state(cfg).values["spec"]
    assert "legacy auth on vpn" in spec["research"]["notes"]
    assert spec["research"]["citations"] == []


def test_missing_key_skip_never_fakes_citations(tmp_path: Path):
    def search(query: str):
        raise MissingSearchKeyError("no key")

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "nokey", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _kind(r) == "hitl_tool"
    assert _payload(r).get("error") == "missing_key"
    r = graph.invoke(Command(resume="skip"), cfg)
    assert _kind(r) != ""
    spec = graph.get_state(cfg).values["spec"]
    assert spec["research"]["citations"] == []
    assert spec["research"]["notes"] == []
    assert r.get("__interrupt__")


def test_budget_error_does_not_end(tmp_path: Path):
    def search(query: str):
        raise WorkerBudgetError("recursion")

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "budget", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _kind(r) == "worker_budget"
    r = graph.invoke(Command(resume="skip"), cfg)
    assert r.get("__interrupt__")
    assert _kind(r) != ""


def test_search_disabled_error(tmp_path: Path):
    def search(query: str):
        raise SearchDisabledError("no live search")

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "disabled", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _payload(r).get("error") == "search_disabled"
    graph.invoke(Command(resume="skip"), cfg)
    spec = graph.get_state(cfg).values["spec"]
    assert spec["research"]["citations"] == []


def test_non_list_search_is_search_failed(tmp_path: Path):
    def search(query: str):
        return {"not": "a list"}

    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "badhits", "search": search}}
    _lock_research(graph, cfg, tmp_path)
    r = graph.invoke(Command(resume="approve"), cfg)
    assert _payload(r).get("error") == "search_failed"
    graph.invoke(Command(resume="skip"), cfg)
    spec = graph.get_state(cfg).values["spec"]
    assert spec["research"]["notes"] == []
