from pathlib import Path

import pytest
from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.graph.session import mkdir_session_child, resolve_session_dir, write_session_file
from homelab_creator.graph.nodes import compose_exists
from homelab_creator.workers.invoke import invoke_worker
from tests.graph.helpers import approve_writes, interrupt_kind as _kind, interrupt_payload as _payload
from tests.spec.factories import beginner_company_spec


def test_invoke_worker_passthrough():
    assert invoke_worker(lambda x: x + 1, 3) == 4


def test_stop_ends_session(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-stop"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="stop"), cfg)
    assert not r.get("__interrupt__")


def test_continue_offers_lock_not_redo(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-lock"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    allowed = _payload(r).get("allowed") or []
    assert "more_brainstorm" in allowed
    assert "lock_idea_and_form" in allowed
    assert "redo_form" not in allowed


def test_offer_then_ask_stop_then_choose(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t1"}}
    r = graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    assert _kind(r) == "offer_idea"
    r = graph.invoke(Command(resume="clinic idea"), cfg)
    assert _kind(r) == "ask_stop"
    r = graph.invoke(Command(resume="continue"), cfg)
    assert _kind(r) == "choose_next_move"


def test_unknown_action_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    r = graph.invoke(Command(resume="not_a_move"), cfg)
    assert _kind(r) == "choose_next_move"
    assert _payload(r).get("error") == "unknown_action"


def test_lock_skips_ask_stop(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t3"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    r = graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    assert _kind(r) == "combined_form"


def test_first_build_shortcut(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t4"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    r = graph.invoke(
        Command(
            resume={
                "action": "submit",
                "vuln_mode": "agent",
                "difficulty": "beginner",
                "research_opted_in": False,
            }
        ),
        cfg,
    )
    assert _kind(r) == "ask_extra_paths"
    r = graph.invoke(Command(resume="no"), cfg)
    assert _kind(r) == "ask_stop"
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    assert _kind(r) == "lab_up"


def test_bad_pick_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-pick"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    r = graph.invoke(Command(resume={"pick": 9}), cfg)
    assert _kind(r) == "offer_idea"
    assert _payload(r).get("error") == "bad_pick"


def test_unknown_ask_stop_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-ask"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="nope"), cfg)
    assert _kind(r) == "ask_stop"
    assert _payload(r).get("error") == "unknown_action"


def test_session_dir_required_and_rejects_parent():
    with pytest.raises(ValueError, match="required"):
        resolve_session_dir({})
    with pytest.raises(ValueError, match=r"\.\."):
        resolve_session_dir({"session_dir": "../escape"})


def test_stale_rebuild_shortcut(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t5"}}
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts_stale = True
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    assert _kind(r) == "lab_up"


def test_unknown_lab_up_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-labup"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    graph.invoke(
        Command(
            resume={
                "action": "submit",
                "vuln_mode": "agent",
                "difficulty": "beginner",
                "research_opted_in": False,
            }
        ),
        cfg,
    )
    graph.invoke(Command(resume="no"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    r = graph.invoke(Command(resume="nope"), cfg)
    assert _kind(r) == "lab_up"
    assert _payload(r).get("error") == "unknown_action"


def test_unknown_extra_paths_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-extra"}}
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  web:\n", encoding="utf-8")
    graph.invoke({"spec": beginner_company_spec().model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    r = graph.invoke(Command(resume="ask_extra_paths"), cfg)
    assert _kind(r) == "ask_extra_paths"
    r = graph.invoke(Command(resume="maybe"), cfg)
    assert _kind(r) == "ask_extra_paths"
    assert _payload(r).get("error") == "unknown_action"


def test_whitespace_idea_dict_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-ws"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    r = graph.invoke(Command(resume={"idea": "   "}), cfg)
    assert _kind(r) == "offer_idea"
    assert _payload(r).get("error") == "empty_idea"


def test_session_dir_rejects_symlink(tmp_path: Path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        resolve_session_dir({"session_dir": str(link)})


def test_unknown_combined_form_reinterrupts(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "t-form"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    graph.invoke(Command(resume="continue"), cfg)
    graph.invoke(Command(resume="lock_idea_and_form"), cfg)
    r = graph.invoke(Command(resume="nope"), cfg)
    assert _kind(r) == "combined_form"
    assert _payload(r).get("error") == "unknown_action"


def test_compose_exists_uses_session_dir_not_spec(tmp_path: Path):
    session = tmp_path / "session"
    session.mkdir()
    compose = session / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    spec = beginner_company_spec()
    spec.artifacts.compose_dir = str(tmp_path / "elsewhere")
    assert compose_exists({"spec": spec.model_dump(), "session_dir": str(session)})
    empty = tmp_path / "empty"
    empty.mkdir()
    spec.artifacts.compose_dir = str(compose)
    assert not compose_exists({"spec": spec.model_dump(), "session_dir": str(empty)})


def test_child_symlink_write_rejected(tmp_path: Path):
    session = tmp_path / "session"
    session.mkdir()
    target = tmp_path / "escape"
    target.mkdir()
    link = session / "writeup.md"
    link.symlink_to(target / "stolen.md")
    with pytest.raises(ValueError, match="symlink"):
        write_session_file(link, "nope\n")
    compose_link = session / "compose"
    compose_link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        mkdir_session_child(session, "compose")


def test_write_rejects_symlink_parent_dir(tmp_path: Path):
    session = tmp_path / "session"
    session.mkdir()
    escape = tmp_path / "escape"
    escape.mkdir()
    compose = session / "compose"
    compose.symlink_to(escape)
    with pytest.raises(ValueError, match="symlink"):
        write_session_file(compose / "docker-compose.yml", "services: {}\n")


def test_write_non_symlink_oserror_not_relabeled(tmp_path: Path):
    session = tmp_path / "session"
    session.mkdir()
    directory = session / "writeup.md"
    directory.mkdir()
    with pytest.raises(OSError):
        write_session_file(directory, "nope\n")
