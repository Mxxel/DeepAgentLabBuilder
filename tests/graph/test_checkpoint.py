from pathlib import Path

from langgraph.types import Command

from homelab_creator.graph.compile import compile_graph
from homelab_creator.graph.state import dump_spec
from tests.spec.factories import beginner_company_spec


def test_sqlite_resume_same_thread(tmp_path: Path):
    db = tmp_path / "checkpoints.sqlite"
    graph = compile_graph(persist_path=db)
    cfg = {"configurable": {"thread_id": "persist1"}}
    graph.invoke({"spec": {}, "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="clinic idea"), cfg)
    graph2 = compile_graph(persist_path=db)
    snap = graph2.get_state(cfg)
    assert snap.values.get("spec", {}).get("idea") == "clinic idea"
    assert snap.interrupts or snap.next


def test_dump_spec_uses_json_enum_values():
    dumped = dump_spec(beginner_company_spec())
    assert dumped["difficulty"] == "beginner"
    assert dumped["lab_up_status"] == "not_run"
    assert dumped["vuln_mode"] == "agent"

