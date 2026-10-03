from pathlib import Path

from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import LabSpec, VulnMode
from homelab_creator.spec.validators import is_plan_ready
from tests.graph.helpers import approve_writes
from tests.spec.factories import beginner_company_spec


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


def _lock_submit(graph, cfg, tmp_path: Path, **fields):
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    resume = {"action": "submit", "research.opted_in": False, **fields}
    return graph.invoke(Command(resume=resume), cfg)


def test_senior_auto_replan_then_extend(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "senior"}}
    r = _lock_submit(graph, cfg, tmp_path, vuln_mode="agent", difficulty="senior_expert")
    assert _kind(r) == "extend_chain"
    allowed = _payload(r).get("allowed") or []
    assert "replan" in allowed
    assert "ask_stop" not in allowed
    r = graph.invoke(Command(resume="replan"), cfg)
    assert _kind(r) == "ask_extra_paths"
    spec = LabSpec.model_validate(graph.get_state(cfg).values["spec"])
    assert is_plan_ready(spec)


def test_extra_path_yes_adds_second_path(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "extra-yes"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="agent", difficulty="beginner")
    r = graph.invoke(Command(resume="yes"), cfg)
    assert _kind(r) == "ask_stop"
    spec = graph.get_state(cfg).values["spec"]
    assert spec["extra_paths_accepted"] is True
    assert len(spec["paths"]) == 2


def test_extra_path_no_keeps_one_path(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "extra-no"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="agent", difficulty="beginner")
    graph.invoke(Command(resume="no"), cfg)
    spec = graph.get_state(cfg).values["spec"]
    assert spec["extra_paths_accepted"] is False
    assert len(spec["paths"]) == 1


def test_user_extend_no_invent_abandon_no_build(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "user-ext"}}
    r = _lock_submit(graph, cfg, tmp_path, vuln_mode="user")
    assert _kind(r) == "extend_chain"
    allowed = _payload(r).get("allowed") or []
    assert set(allowed) == {"switch_to_both", "add_hops", "abandon_generation"}
    r = graph.invoke(Command(resume="abandon_generation"), cfg)
    assert _kind(r) == "choose_next_move"
    assert "build" not in (_payload(r).get("allowed") or [])
    spec = graph.get_state(cfg).values["spec"]
    assert spec["hosts"] == []
    r = graph.invoke(Command(resume="more_brainstorm"), cfg)
    assert _kind(r) == "offer_idea"


def test_not_plan_ready_continue_does_not_first_build(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "no-build"}}
    graph.invoke(
        {"spec": beginner_company_spec().model_dump() | {"hosts": [], "paths": []}, "session_dir": str(tmp_path)},
        cfg,
    )
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert _kind(r) == "choose_next_move"
    assert "build" not in (_payload(r).get("allowed") or [])


def test_redo_sets_stale_and_continue_rebuilds(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "stale-redo"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="agent", difficulty="beginner")
    graph.invoke(Command(resume="no"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    graph.invoke(Command(resume="skip"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert _kind(r) == "choose_next_move"
    graph.invoke(Command(resume="redo_form"), cfg)
    graph.invoke(
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
    graph.invoke(Command(resume="no"), cfg)
    assert graph.get_state(cfg).values["spec"]["artifacts_stale"] is True
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    assert _kind(r) == "lab_up"


def test_switch_to_both_defaults_beginner(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "switch-both"}}
    r = _lock_submit(graph, cfg, tmp_path, vuln_mode="user")
    assert _kind(r) == "extend_chain"
    r = graph.invoke(Command(resume="switch_to_both"), cfg)
    assert _kind(r) == "ask_extra_paths"
    spec = LabSpec.model_validate(graph.get_state(cfg).values["spec"])
    assert spec.vuln_mode == VulnMode.both
    assert spec.difficulty.value == "beginner"
    assert is_plan_ready(spec)


def test_switch_to_both_rejects_user_defined(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "switch-bad"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="user")
    r = graph.invoke(Command(resume={"action": "switch_to_both", "difficulty": "user_defined"}), cfg)
    assert _kind(r) == "extend_chain"
    assert _payload(r).get("error") == "bad_difficulty"


def test_add_hops_keeps_user_chain_then_fills(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "add-hops"}}
    r = _lock_submit(graph, cfg, tmp_path, vuln_mode="agent", difficulty="senior_expert")
    assert _kind(r) == "extend_chain"
    r = graph.invoke(
        Command(
            resume={
                "action": "add_hops",
                "hosts": [
                    {"id": "edge", "role": "foothold", "stack": ["nginx"], "vulns": ["xss"]},
                    {"id": "mid", "role": "internal", "stack": ["app"], "vulns": ["sqli"]},
                    {"id": "core", "role": "crown_jewel", "stack": ["ad"], "vulns": ["acl"]},
                ],
                "hops": ["edge", "mid", "core"],
                "vulns": ["phish"],
            }
        ),
        cfg,
    )
    assert _kind(r) == "ask_extra_paths"
    spec = LabSpec.model_validate(graph.get_state(cfg).values["spec"])
    ids = [h.id for h in spec.hosts]
    assert ids[:3] == ["edge", "mid", "core"]
    assert "phish" in spec.hosts[0].vulns
    assert is_plan_ready(spec)


def test_add_hops_bad_role_reprompts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "bad-host"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="user")
    r = graph.invoke(
        Command(resume={"action": "add_hops", "hosts": [{"id": "x", "role": "custom_box"}]}),
        cfg,
    )
    assert _kind(r) == "extend_chain"
    assert _payload(r).get("error") == "bad_hosts"


def test_add_hops_unknown_hop_reprompts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "bad-hop"}}
    _lock_submit(graph, cfg, tmp_path, vuln_mode="user")
    r = graph.invoke(
        Command(
            resume={
                "action": "add_hops",
                "hosts": [
                    {"id": "web", "role": "foothold", "stack": ["nginx"], "vulns": ["x"]},
                    {"id": "app", "role": "internal", "stack": ["app"], "vulns": ["y"]},
                ],
                "hops": ["web", "ghost"],
            }
        ),
        cfg,
    )
    assert _kind(r) == "extend_chain"
    assert _payload(r).get("error") == "bad_hops"
