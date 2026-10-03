from pathlib import Path

from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import LabSpec, LabUpStatus
from homelab_creator.tui.headless import ScriptedTUI
from homelab_creator.tui.session import run_session


def _form_submit():
    return {
        "action": "submit",
        "vuln_mode": "agent",
        "difficulty": "beginner",
        "research.opted_in": False,
    }


def test_scripted_session_lock_form_build_skip_stop(tmp_path: Path):
    tui = ScriptedTUI(
        [
            "clinic idea",
            "continue",
            "lock_idea_and_form",
            _form_submit(),
            "no",
            "continue",
            "skip",
            "stop",
        ]
    )
    graph = compile_graph()
    result = run_session(tui, session_dir=tmp_path, thread_id="script-stop", graph=graph)
    assert not result.get("__interrupt__")
    kinds = [p.get("interrupt_kind") for p in tui.shown]
    assert kinds[0] == "offer_idea"
    assert "choose_next_move" in kinds
    assert "combined_form" in kinds
    assert "ask_extra_paths" in kinds
    assert "lab_up" in kinds
    assert kinds.count("hitl_tool") >= 2
    spec = LabSpec.model_validate(graph.get_state({"configurable": {"thread_id": "script-stop"}}).values["spec"])
    assert spec.lab_up_status == LabUpStatus.skipped
    assert any("Planner:" in line or "planner" in line.lower() for line in tui.progress_lines)


def test_scripted_session_skip_then_rebuild_not_lock(tmp_path: Path):
    tui = ScriptedTUI(
        [
            "clinic idea",
            "continue",
            "lock_idea_and_form",
            _form_submit(),
            "no",
            "continue",
            "skip",
            "continue",
        ],
        pause_when_exhausted=True,
    )
    run_session(tui, session_dir=tmp_path, thread_id="script-rebuild")
    last = tui.shown[-1]
    assert last.get("interrupt_kind") == "choose_next_move"
    allowed = last.get("allowed") or []
    assert "rebuild" in allowed
    assert "lab_up" in allowed
    assert "lock_idea_and_form" not in allowed
    assert "redo_form" in allowed


def test_scripted_redo_then_continue_rebuilds(tmp_path: Path):
    tui = ScriptedTUI(
        [
            "clinic idea",
            "continue",
            "lock_idea_and_form",
            _form_submit(),
            "no",
            "continue",
            "skip",
            "continue",
            "redo_form",
            _form_submit(),
            "no",
            "continue",
            "skip",
        ],
        pause_when_exhausted=True,
    )
    run_session(tui, session_dir=tmp_path, thread_id="script-redo")
    kinds = [p.get("interrupt_kind") for p in tui.shown]
    assert kinds[-1] == "ask_stop"
    assert kinds.count("lab_up") >= 2


def test_lab_up_up_uses_injected_compose_cli(tmp_path: Path):
    calls: list[list[str]] = []

    def runner(cmd, cwd):
        calls.append(list(cmd))
        return 0, "ok"

    tui = ScriptedTUI(
        [
            "clinic idea",
            "continue",
            "lock_idea_and_form",
            _form_submit(),
            "no",
            "continue",
            "up",
            "stop",
        ]
    )
    graph = compile_graph()
    run_session(
        tui,
        session_dir=tmp_path,
        thread_id="script-up",
        graph=graph,
        configurable={"compose_cli": runner},
    )
    assert calls
    assert calls[0][:3] == ["docker", "compose", "-f"]
    assert "--detach" in calls[0]
    spec = LabSpec.model_validate(graph.get_state({"configurable": {"thread_id": "script-up"}}).values["spec"])
    assert spec.lab_up_status == LabUpStatus.running
