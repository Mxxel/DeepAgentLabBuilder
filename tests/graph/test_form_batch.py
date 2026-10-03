from pathlib import Path

from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import VulnMode
from tests.graph.helpers import approve_writes
from tests.spec.factories import STUB_CITATION, STUB_NOTE


def fake_search(_query: str):
    fake_search.calls.append(_query)
    return [{"title": "Edge", "url": STUB_CITATION, "snippet": STUB_NOTE}]


fake_search.calls = []


def _kind(result) -> str:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return ""
    first = interrupts[0]
    value = getattr(first, "value", first)
    if isinstance(value, dict):
        return str(value.get("interrupt_kind") or "")
    return ""


def _lock_form(graph, cfg, tmp_path: Path, resume: dict):
    fake_search.calls = []
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    return graph.invoke(Command(resume=resume), cfg)


def test_form_resume_starts_batch_not_ask_stop(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "form-batch"}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": False,
        },
    )
    assert _kind(r) == "ask_extra_paths"


def test_research_notes_reach_planner_only_if_opted_in(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "notes-yes", "search": fake_search}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": True,
        },
    )
    assert _kind(r) == "hitl_tool"
    r = graph.invoke(Command(resume="approve"), cfg)
    values = graph.get_state(cfg).values
    assert STUB_NOTE in (values.get("planner_input_notes") or [])
    assert values["spec"]["research"]["opted_in"] is True
    assert values["spec"]["research"]["notes"]
    vulns = " ".join(v for h in values["spec"]["hosts"] for v in h.get("vulns") or [])
    assert "research class:" in vulns
    assert STUB_NOTE[:40] in vulns

    cfg2 = {"configurable": {"thread_id": "notes-no"}}
    _lock_form(
        graph,
        cfg2,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": False,
        },
    )
    skipped = graph.get_state(cfg2).values
    assert skipped.get("planner_input_notes") == []
    assert skipped["spec"]["research"]["notes"] == []


def test_user_vulns_retained_in_both(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "both-vulns"}}
    _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "both",
            "difficulty": "beginner",
            "research.opted_in": False,
            "user_vulns": ["user-named xss"],
        },
    )
    spec = graph.get_state(cfg).values["spec"]
    assert spec["vuln_mode"] == VulnMode.both.value
    assert "user-named xss" in spec["user_vulns"]
    assert "user-named xss" in spec["hosts"][0]["vulns"]
    assert len(spec["paths"]) == 1


def test_user_only_invalid_goes_to_extend_chain(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "user-invalid"}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {"action": "submit", "vuln_mode": "user", "research.opted_in": False},
    )
    assert _kind(r) == "extend_chain"


def test_string_false_does_not_opt_in_research(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "false-str"}}
    _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": "false",
        },
    )
    values = graph.get_state(cfg).values
    assert values["spec"]["research"]["opted_in"] is False
    assert values.get("planner_input_notes") == []


def test_nested_research_opted_in(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "nested-opt", "search": fake_search}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research": {"opted_in": True},
        },
    )
    assert _kind(r) == "hitl_tool"
    graph.invoke(Command(resume="approve"), cfg)
    values = graph.get_state(cfg).values
    assert values["spec"]["research"]["opted_in"] is True
    assert values.get("planner_input_notes")


def test_bad_opted_in_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "bad-opt"}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": "nope",
        },
    )
    assert _kind(r) == "combined_form"
    assert _payload(r).get("error") == "bad_research_opted_in"


def test_bad_user_vulns_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "bad-vulns"}}
    r = _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "both",
            "difficulty": "beginner",
            "research.opted_in": False,
            "user_vulns": [1, "ok"],
        },
    )
    assert _kind(r) == "combined_form"
    assert _payload(r).get("error") == "bad_user_vulns"


def test_redo_form_reruns_batch_not_ask_stop(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "redo"}}
    _lock_form(
        graph,
        cfg,
        tmp_path,
        {
            "action": "submit",
            "vuln_mode": "agent",
            "difficulty": "beginner",
            "research.opted_in": False,
        },
    )
    graph.invoke(Command(resume="no"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    graph.invoke(Command(resume="skip"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert _kind(r) == "choose_next_move"
    assert "redo_form" in (_payload(r).get("allowed") or [])
    r = graph.invoke(Command(resume="redo_form"), cfg)
    assert _kind(r) == "combined_form"
    r = graph.invoke(
        Command(
            resume={
                "action": "submit",
                "vuln_mode": "agent",
                "difficulty": "beginner",
                "research.opted_in": False,
            }
        ),
        cfg,
    )
    assert _kind(r) == "ask_extra_paths"


def _payload(result) -> dict:
    interrupts = result.get("__interrupt__") or []
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {}
