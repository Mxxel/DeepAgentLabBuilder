from pathlib import Path

from langgraph.types import Command

from homelab_creator.catalog.render import render_compose
from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.validators import is_artifact_ready, is_plan_ready
from homelab_creator.workers.writeup import render_writeup, run_writeup
from tests.graph.helpers import approve_writes, interrupt_kind, interrupt_payload
from tests.spec.factories import STUB_CITATION, STUB_NOTE, beginner_company_spec


def test_missing_writeup_is_not_artifact_ready():
    spec = beginner_company_spec()
    assert is_plan_ready(spec)
    assert not spec.artifacts.writeup_path
    assert not is_artifact_ready(spec)


def test_citations_empty_iff_research_skipped():
    spec = beginner_company_spec()
    skipped = render_writeup(spec)
    assert "## Citations" not in skipped
    assert STUB_CITATION not in skipped
    spec.research.opted_in = True
    spec.research.notes = [STUB_NOTE]
    spec.research.citations = [STUB_CITATION]
    researched = render_writeup(spec)
    assert STUB_NOTE in researched
    assert STUB_CITATION in researched
    assert "## Citations" in researched


def test_writeup_inventory_and_hops():
    spec = beginner_company_spec()
    text = render_writeup(spec)
    for host in spec.hosts:
        assert host.id in text
        assert host.role in text
    assert "web -> app -> dc" in text


def test_plan_ready_without_compose_first_builds(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "first-build"}}
    spec = beginner_company_spec()
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert interrupt_kind(r) == "hitl_tool"
    assert interrupt_payload(r).get("tool") == "write_session_files"
    assert is_plan_ready(spec)
    assert not (tmp_path / "compose").exists()


def test_generated_writeup_with_compose_is_artifact_ready(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text(render_compose(spec), encoding="utf-8")
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nweb app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text(render_writeup(spec), encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    assert is_artifact_ready(spec)


def test_writeup_skip_when_not_plan_ready(tmp_path: Path):
    from homelab_creator.workers.invoke import WorkerOutcome
    from homelab_creator.spec.models import Host, LabSpec, VulnMode

    spec = LabSpec(
        vuln_mode=VulnMode.user,
        hosts=[Host(id="web", role="foothold", stack=["nginx"], vulns=["x"])],
    )
    assert run_writeup(spec, session=tmp_path) is WorkerOutcome.skip
    assert not (tmp_path / "writeup.md").exists()


def test_stale_rebuild_clears_after_artifact_ready(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "writeup-stale"}}
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text(render_compose(spec), encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts_stale = True
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = approve_writes(graph, cfg, r)
    assert interrupt_kind(r) == "lab_up"
    out = LabSpec.model_validate(graph.get_state(cfg).values["spec"])
    assert out.artifacts_stale is False
    assert is_artifact_ready(out)
    writeup = Path(out.artifacts.writeup_path).read_text(encoding="utf-8")
    assert "## Citations" not in writeup
    for host in out.hosts:
        assert host.id in writeup


def test_writeup_reject_does_not_lab_up(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "writeup-reject"}}
    spec = beginner_company_spec()
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert interrupt_payload(r).get("tool") == "write_session_files"
    r = graph.invoke(Command(resume="approve"), cfg)
    assert interrupt_kind(r) == "hitl_tool"
    r = graph.invoke(Command(resume="reject"), cfg)
    assert interrupt_kind(r) == "ask_stop"
    assert not (tmp_path / "writeup.md").exists()
    spec = LabSpec.model_validate(graph.get_state(cfg).values["spec"])
    assert spec.artifacts_stale is True
    assert not is_artifact_ready(spec)
