"""Golden spec validator cases."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from homelab_creator.spec.models import CompromisePath, Difficulty, Host, LabSpec, VulnMode
from homelab_creator.spec.validators import (
    artifact_ready_errors,
    compose_file,
    is_artifact_ready,
    is_plan_ready,
    plan_ready_errors,
)
from tests.spec.factories import STUB_CITATION, beginner_company_spec


def test_empty_spec_not_plan_ready():
    assert is_plan_ready(LabSpec()) is False
    assert "no hosts" in plan_ready_errors(LabSpec())


def test_beginner_company_plan_ready():
    spec = beginner_company_spec()
    assert is_plan_ready(spec)
    assert not spec.artifacts.compose_dir


def test_extra_path_requires_acceptance():
    spec = beginner_company_spec(extra_path=True)
    spec.extra_paths_accepted = False
    assert not is_plan_ready(spec)
    spec.extra_paths_accepted = True
    assert is_plan_ready(spec)


def test_agent_mode_enforces_minima_and_roles():
    spec = beginner_company_spec()
    spec.hosts = spec.hosts[:2]
    assert any("hosts" in e for e in plan_ready_errors(spec))
    with pytest.raises(ValidationError):
        Host(id="dc", role="custom_box", stack=["samba"], vulns=["x"])
    spec = beginner_company_spec()
    spec.hosts[2] = Host.model_construct(
        id="dc",
        role="custom_box",
        networks=["int"],
        stack=["samba"],
        vulns=["unconstrained delegation class"],
    )
    assert any("non-catalog" in e for e in plan_ready_errors(spec))


def test_user_defined_skips_minima_but_three_roles_plan_ready():
    spec = beginner_company_spec()
    spec.difficulty = Difficulty.user_defined
    spec.vuln_mode = VulnMode.agent
    spec.hosts = spec.hosts[:2]
    spec.paths = [CompromisePath(hops=["web", "app"])]
    assert "need at least" not in " ".join(plan_ready_errors(spec))
    spec = beginner_company_spec()
    spec.difficulty = Difficulty.user_defined
    spec.vuln_mode = VulnMode.user
    assert is_plan_ready(spec)


def test_user_only_invalid_chain_not_plan_ready():
    spec = LabSpec(
        vuln_mode=VulnMode.user,
        difficulty=Difficulty.user_defined,
        hosts=[Host(id="web", role="foothold", stack=["nginx"], vulns=["default creds"])],
        paths=[],
    )
    assert not is_plan_ready(spec)


def test_user_mode_one_host_with_path_not_plan_ready():
    spec = LabSpec(
        vuln_mode=VulnMode.user,
        difficulty=Difficulty.user_defined,
        hosts=[Host(id="web", role="foothold", stack=["nginx"], vulns=["default creds"])],
        paths=[CompromisePath(hops=["web"])],
    )
    assert not is_plan_ready(spec)
    assert any("single-service" in e for e in plan_ready_errors(spec))


def test_empty_hops_and_unknown_hops_not_plan_ready():
    spec = beginner_company_spec()
    spec.vuln_mode = VulnMode.user
    spec.paths = [CompromisePath(hops=[])]
    assert any("no hops" in e for e in plan_ready_errors(spec))
    spec.paths = [CompromisePath(hops=["ghost"])]
    assert any("not host ids" in e for e in plan_ready_errors(spec))


def test_plan_ready_without_compose_does_not_need_writeup():
    spec = beginner_company_spec()
    assert is_plan_ready(spec)
    assert not spec.artifacts.writeup_path


def test_artifact_ready_needs_files(tmp_path: Path):
    spec = beginner_company_spec()
    assert not is_artifact_ready(spec)
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  web:\n  app:\n  dc:\n", encoding="utf-8")
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nweb app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text("web app dc\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    assert is_artifact_ready(spec)


def test_artifact_rejects_host_net_privileged_and_poc(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "c"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  web:\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(tmp_path / "t.md")
    spec.artifacts.writeup_path = str(tmp_path / "w.md")
    (tmp_path / "t.md").write_text("x", encoding="utf-8")
    (tmp_path / "w.md").write_text("x", encoding="utf-8")
    errs = artifact_ready_errors(
        spec,
        compose_text='network_mode: "host"\nprivileged: True\n',
        writeup_text="exploit PoC for web",
    )
    assert any("host network" in e for e in errs)
    assert any("privileged" in e for e in errs)
    assert any("PoC" in e for e in errs)


def test_artifact_ready_reads_files_when_kwargs_omitted(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text(
        'services:\n  web:\n    network_mode: "host"\n  app:\n  dc:\n',
        encoding="utf-8",
    )
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nweb app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text("web app dc\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    errs = artifact_ready_errors(spec)
    assert any("host network" in e for e in errs)


def test_empty_host_id_rejected():
    spec = beginner_company_spec()
    spec.hosts[0] = spec.hosts[0].model_copy(update={"id": ""})
    assert any("empty host id" in e for e in plan_ready_errors(spec))


def test_host_id_not_substring_false_positive(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  webhook:\n  app:\n  dc:\n", encoding="utf-8")
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nwebhook app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text("webhook app dc\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    errs = artifact_ready_errors(spec)
    assert any("host web missing from compose" in e for e in errs)
    assert any("host web missing from topology" in e for e in errs)
    assert any("host web missing from writeup" in e for e in errs)


def test_host_must_have_stack_and_vulns():
    spec = LabSpec(
        hosts=[Host(id="a", role="foothold")],
        paths=[CompromisePath(hops=["a"])],
    )
    errs = plan_ready_errors(spec)
    assert any("stack" in e for e in errs)
    assert any("vulns" in e for e in errs)


def test_empty_compose_file_is_not_artifact_ready(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("", encoding="utf-8")
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nweb app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text("", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    errs = artifact_ready_errors(spec)
    assert any("host web missing from compose" in e for e in errs)
    assert any("host web missing from writeup" in e for e in errs)


def test_writeup_isolation_words_do_not_fail_compose_rules(tmp_path: Path):
    spec = beginner_company_spec()
    compose = tmp_path / "compose"
    compose.mkdir()
    (compose / "docker-compose.yml").write_text("services:\n  web:\n  app:\n  dc:\n", encoding="utf-8")
    topo = tmp_path / "topology.md"
    topo.write_text("# t\nweb app dc\n", encoding="utf-8")
    writeup = tmp_path / "writeup.md"
    writeup.write_text("web app dc — do not use network_mode: host or privileged: true\n", encoding="utf-8")
    spec.artifacts.compose_dir = str(compose)
    spec.artifacts.topology_path = str(topo)
    spec.artifacts.writeup_path = str(writeup)
    assert is_artifact_ready(spec)


def test_hyphenated_poc_marker():
    spec = beginner_company_spec()
    errs = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n  app:\n  dc:\n",
        writeup_text="web app dc exploit-PoC",
    )
    assert any("PoC" in e for e in errs)


def test_duplicate_host_ids_not_plan_ready():
    spec = beginner_company_spec()
    spec.hosts[1] = spec.hosts[1].model_copy(update={"id": "web"})
    assert any("duplicate host id" in e for e in plan_ready_errors(spec))


def test_isolation_ignores_comments_and_hostname():
    spec = beginner_company_spec()
    errs = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    network_mode: hostname\n  # network_mode: host\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert not any("host network" in e for e in errs)


def test_privileged_yes_forbidden():
    spec = beginner_company_spec()
    errs = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    privileged: yes\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("privileged" in e for e in errs)


def test_compose_file_ignores_symlink(tmp_path: Path):
    compose = tmp_path / "compose"
    compose.mkdir()
    real = tmp_path / "real.yml"
    real.write_text("services: {}\n", encoding="utf-8")
    (compose / "docker-compose.yml").symlink_to(real)
    assert compose_file(compose) is None


def test_host_port_publish_and_host_bind_forbidden():
    spec = beginner_company_spec()
    errs = artifact_ready_errors(
        spec,
        compose_text='services:\n  web:\n    ports:\n      - "8080:80"\n    volumes:\n      - /etc/passwd:/x\n  app:\n  dc:\n',
        writeup_text="web app dc",
    )
    assert any("host port" in e for e in errs)
    assert any("host bind" in e for e in errs)
    loopback = artifact_ready_errors(
        spec,
        compose_text='services:\n  web:\n    ports:\n      - "127.0.0.1:8080:80"\n  app:\n  dc:\n',
        writeup_text="web app dc",
    )
    assert any("host port" in e for e in loopback)
    all_ifaces = artifact_ready_errors(
        spec,
        compose_text='services:\n  web:\n    ports:\n      - "0.0.0.0:8080:80"\n  app:\n  dc:\n',
        writeup_text="web app dc",
    )
    assert any("host port" in e for e in all_ifaces)
    long_form = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    ports:\n      - target: 80\n        published: 8080\n        host_ip: 0.0.0.0\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("host port" in e for e in long_form)


def test_reserved_compose_ids_not_plan_ready():
    spec = beginner_company_spec()
    spec.hosts[0] = spec.hosts[0].model_copy(update={"id": "ports"})
    spec.paths[0] = spec.paths[0].model_copy(update={"hops": ["ports", "app", "dc"]})
    assert any("unsafe host id" in e for e in plan_ready_errors(spec))


def test_citation_missing_when_research_opted_in():
    spec = beginner_company_spec()
    spec.research.opted_in = True
    spec.research.citations = [STUB_CITATION]
    errs = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("citation missing" in e for e in errs)
    errs_ok = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n  app:\n  dc:\n",
        writeup_text=f"web app dc\n{STUB_CITATION}\n",
    )
    assert not any("citation missing" in e for e in errs_ok)


def test_citations_heading_fails_when_research_skipped():
    spec = beginner_company_spec()
    errs = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n  app:\n  dc:\n",
        writeup_text="web app dc\n## Citations\n- http://x.invalid\n",
    )
    assert any("research skipped" in e for e in errs)


def test_folded_privileged_and_tagged_bool_forbidden():
    spec = beginner_company_spec()
    folded = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    privileged: >\n      true\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("privileged" in e for e in folded)
    tagged = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    privileged: !!bool true\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("privileged" in e for e in tagged)
    host_ip = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    ports:\n      - target: 80\n        host_ip: 127.0.0.1\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("host port" in e for e in host_ip)


def test_interpolation_and_mapping_bind_forbidden():
    spec = beginner_company_spec()
    interp = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    network_mode: ${NM:-host}\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("interpolation" in e or "host network" in e for e in interp)
    mapping = artifact_ready_errors(
        spec,
        compose_text="services:\n  web:\n    volumes:\n      - source: /etc/passwd\n        target: /x\n  app:\n  dc:\n",
        writeup_text="web app dc",
    )
    assert any("host bind" in e for e in mapping)
