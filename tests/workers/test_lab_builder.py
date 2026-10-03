from pathlib import Path

from langgraph.types import Command

from homelab_creator.catalog.render import ALLOWED_IMAGES, assign_host_ips, render_compose, render_lab, render_topology
from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.models import Host, LabSpec, VulnMode
from homelab_creator.spec.validators import artifact_ready_errors
from homelab_creator.workers.invoke import WorkerOutcome
from homelab_creator.workers.lab_builder import run_lab_builder
from tests.graph.helpers import approve_writes, interrupt_kind, interrupt_payload
from tests.spec.factories import beginner_company_spec


def test_catalog_compose_matches_topology_and_isolation():
    spec = beginner_company_spec()
    files = render_lab(spec)
    compose = files["compose/docker-compose.yml"]
    topology = files["topology.md"]
    for host in spec.hosts:
        assert f"  {host.id}:" in compose
        assert host.id in topology
    for line in compose.splitlines():
        if "image:" in line:
            assert line.split(":", 1)[1].strip() in ALLOWED_IMAGES
    assert "ports:" not in compose
    assert "127.0.0.1" not in compose
    assert "0.0.0.0" not in compose
    assert "ipv4_address:" in compose
    assert "network_mode: host" not in compose
    assert "privileged:" not in compose
    assert "driver: bridge" in compose
    ips = assign_host_ips(spec)
    for host in spec.hosts:
        for ip in ips[host.id].values():
            assert ip in compose
            assert ip in topology
    errs = artifact_ready_errors(spec, compose_text=compose, writeup_text="web app dc")
    assert not any("host network" in e or "privileged" in e or "host port" in e or "host bind" in e for e in errs)


def test_single_host_not_plan_ready_so_builder_skips(tmp_path: Path):
    spec = LabSpec(
        vuln_mode=VulnMode.user,
        hosts=[Host(id="web", role="foothold", stack=["nginx"], vulns=["default creds"])],
        paths=[],
    )
    assert run_lab_builder(spec, session=tmp_path) is WorkerOutcome.skip
    assert not (tmp_path / "compose" / "docker-compose.yml").exists()


def test_multi_instance_unique_service_names():
    spec = beginner_company_spec()
    spec.hosts.append(Host(id="workstation-1", role="workstation", stack=["workstation"], vulns=["phish"]))
    spec.hosts.append(Host(id="workstation-2", role="workstation", stack=["workstation"], vulns=["phish"]))
    compose = render_compose(spec)
    assert "  workstation-1:" in compose
    assert "  workstation-2:" in compose
    assert render_topology(spec).count("workstation-1")


def test_lab_builder_hitl_approve_writes_files(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "lab-hitl"}}
    spec = beginner_company_spec()
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    assert interrupt_kind(r) == "hitl_tool"
    assert interrupt_payload(r).get("tool") == "write_session_files"
    r = approve_writes(graph, cfg, r)
    assert interrupt_kind(r) == "lab_up"
    compose = (tmp_path / "compose" / "docker-compose.yml").read_text(encoding="utf-8")
    topo = (tmp_path / "topology.md").read_text(encoding="utf-8")
    assert "  web:" in compose
    assert "web" in topo
    assert "ipv4_address:" in compose
    assert "ports:" not in compose


def test_lab_builder_reject_skips_writeup(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "lab-reject"}}
    spec = beginner_company_spec()
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    r = graph.invoke(Command(resume="reject"), cfg)
    assert interrupt_kind(r) == "ask_stop"
    assert not (tmp_path / "compose" / "docker-compose.yml").exists()


def test_lab_builder_edit_rejects_host_ports(tmp_path: Path):
    graph = compile_graph()
    cfg = {"configurable": {"thread_id": "lab-edit"}}
    spec = beginner_company_spec()
    graph.invoke({"spec": spec.model_dump(), "session_dir": str(tmp_path)}, cfg)
    graph.invoke(Command(resume="idea"), cfg)
    r = graph.invoke(Command(resume="continue"), cfg)
    files = dict(interrupt_payload(r).get("args", {}).get("files") or {})
    files["compose/docker-compose.yml"] = files["compose/docker-compose.yml"].replace(
        "expose: [80]",
        'ports:\n      - "127.0.0.1:8080:80"',
    )
    r = graph.invoke(Command(resume={"action": "edit", "args": {"files": files}}), cfg)
    assert interrupt_kind(r) == "hitl_tool"
    assert interrupt_payload(r).get("error") == "isolation"
    assert interrupt_payload(r).get("allowed_decisions") == ["approve", "edit", "reject"]
