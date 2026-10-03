from homelab_creator.spec.models import Difficulty, Host, LabSpec, VulnMode
from homelab_creator.spec.validators import is_plan_ready, plan_ready_errors
from homelab_creator.workers.planner import run_planner


def test_beginner_floor_is_plan_ready():
    spec = LabSpec(vuln_mode=VulnMode.agent, difficulty=Difficulty.beginner)
    out = run_planner(spec, fill="floor")
    assert is_plan_ready(out)
    assert len(out.hosts) == 3
    assert len(out.paths[0].hops) == 3


def test_senior_floor_fails_minima_full_passes():
    spec = LabSpec(vuln_mode=VulnMode.agent, difficulty=Difficulty.senior_expert)
    floor = run_planner(spec, fill="floor")
    assert not is_plan_ready(floor)
    assert any("hosts" in e or "hops" in e for e in plan_ready_errors(floor))
    full = run_planner(floor, fill="minima")
    assert is_plan_ready(full)
    assert len(full.hosts) >= 6
    assert len(full.paths[0].hops) >= 6


def test_user_mode_does_not_invent():
    spec = LabSpec(vuln_mode=VulnMode.user, difficulty=Difficulty.user_defined)
    out = run_planner(spec, fill="minima")
    assert out.hosts == []
    assert not is_plan_ready(out)


def test_inventing_user_defined_becomes_beginner():
    spec = LabSpec(vuln_mode=VulnMode.both, difficulty=Difficulty.user_defined, user_vulns=["phish"])
    out = run_planner(spec, fill="minima")
    assert out.difficulty == Difficulty.beginner
    assert is_plan_ready(out)
    assert "phish" in out.hosts[0].vulns
    assert "default creds" in out.hosts[0].vulns


def test_fill_keeps_supplied_hosts():
    spec = LabSpec(
        vuln_mode=VulnMode.agent,
        difficulty=Difficulty.beginner,
        user_vulns=["phish"],
        hosts=[Host(id="edge", role="foothold", stack=["nginx"], vulns=["xss"])],
    )
    out = run_planner(spec, fill="floor")
    assert "edge" in [h.id for h in out.hosts]
    foothold = next(h for h in out.hosts if h.id == "edge")
    assert "phish" in foothold.vulns
    assert "xss" in foothold.vulns
    assert is_plan_ready(out)


def test_extra_instance_ids_are_suffixed():
    spec = LabSpec(vuln_mode=VulnMode.agent, difficulty=Difficulty.senior_expert)
    out = run_planner(spec, fill="minima")
    ids = [h.id for h in out.hosts]
    assert "workstation-1" in ids
    assert "mail-1" in ids
    assert "jump-1" in ids
