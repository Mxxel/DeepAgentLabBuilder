"""Vuln planner: catalog roles, difficulty minima for agent/both only."""

from __future__ import annotations

from homelab_creator.spec.models import (
    DIFFICULTY_MINIMA,
    EXTRA_ROLES,
    REQUIRED_ROLES,
    CompromisePath,
    Difficulty,
    Host,
    LabSpec,
    Network,
    VulnMode,
)
from homelab_creator.spec.safety import contains_poc
from homelab_creator.workers.llm import live_llm_enabled
from homelab_creator.tui.progress import emit

FLOOR_HOSTS = 3
FLOOR_HOPS = 2
VULN_BY_DIFFICULTY = {
    "beginner": "default creds",
    "intermediate": "weak session handling",
    "advanced": "subtle ACL gap",
    "senior_expert": "segmented trust abuse",
}


def _host_slots(count: int) -> list[tuple[str, str]]:
    slots = [("web", "foothold"), ("app", "internal"), ("dc", "crown_jewel")]
    extra_n = 1
    while len(slots) < count:
        for role in EXTRA_ROLES:
            slots.append((f"{role}-{extra_n}", role))
            if len(slots) >= count:
                break
        extra_n += 1
    return slots[:count]


def _make_host(host_id: str, role: str, vuln: str, user_vulns: list[str], foothold: bool) -> Host:
    host_vulns = [vuln]
    if foothold and user_vulns:
        host_vulns = list(user_vulns) + host_vulns
    return Host(
        id=host_id,
        role=role,  # type: ignore[arg-type]
        networks=["dmz"] if foothold else ["int"],
        stack=[role],
        vulns=host_vulns,
    )


def _repair_host(host: Host, vuln: str, user_vulns: list[str], foothold: bool) -> Host:
    current = host.model_copy(deep=True)
    if not current.stack:
        current.stack = [current.role]
    if not current.vulns:
        current.vulns = [vuln]
    if foothold and user_vulns:
        for item in reversed(user_vulns):
            if item not in current.vulns:
                current.vulns.insert(0, item)
    return current


def _fresh_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    n = 2
    while f"{base}-{n}" in used:
        n += 1
    return f"{base}-{n}"


def _build_hosts(count: int, vuln: str, user_vulns: list[str]) -> list[Host]:
    hosts: list[Host] = []
    for i, (host_id, role) in enumerate(_host_slots(count)):
        hosts.append(_make_host(host_id, role, vuln, user_vulns, foothold=i == 0))
    return hosts


def _primary_path(hosts: list[Host], hops: int, existing: list[str] | None = None) -> CompromisePath:
    nodes = max(hops + 1, 2)
    host_ids = [h.id for h in hosts]
    known = set(host_ids)
    ids = [hop for hop in (existing or []) if hop in known]
    for hid in host_ids:
        if len(ids) >= nodes:
            break
        if hid not in ids:
            ids.append(hid)
    if len(ids) < 2 and hosts:
        ids = [hosts[0].id, hosts[-1].id]
    return CompromisePath(hops=ids[: max(nodes, len(ids))])


def _finding_class(spec: LabSpec) -> str:
    base = VULN_BY_DIFFICULTY.get(spec.difficulty.value, "misconfig")
    if spec.research.opted_in:
        for note in spec.research.notes:
            text = note.strip()
            if text and not contains_poc(text):
                return f"{base}; research class: {text[:120]}"
    return base


def fill_to(spec: LabSpec, *, hosts: int, hops: int) -> LabSpec:
    """Grow an agent or both spec to the requested host and hop counts.

    User-only specs are returned unchanged. Existing hosts and user-named issues are kept.
    """
    current = spec.model_copy(deep=True)
    if current.vuln_mode == VulnMode.user:
        return current
    vuln = _finding_class(current)
    user_vulns = list(current.user_vulns)
    merged: list[Host] = []
    used_ids: set[str] = set()
    for host in current.hosts:
        if host.id in used_ids:
            continue
        foothold = host.role == "foothold" or not merged
        merged.append(_repair_host(host, vuln, user_vulns, foothold=foothold))
        used_ids.add(host.id)
    roles = {h.role for h in merged}
    for host_id, role in [("web", "foothold"), ("app", "internal"), ("dc", "crown_jewel")]:
        if role not in roles:
            hid = _fresh_id(host_id, used_ids)
            merged.append(_make_host(hid, role, vuln, user_vulns, foothold=role == "foothold"))
            used_ids.add(hid)
            roles.add(role)
    have_roles = {h.role for h in merged}
    for host_id, role in _host_slots(max(hosts * 2, 16)):
        if len(merged) >= hosts:
            break
        if host_id in used_ids:
            continue
        if role in REQUIRED_ROLES and role in have_roles:
            continue
        merged.append(_make_host(host_id, role, vuln, user_vulns, foothold=False))
        used_ids.add(host_id)
        have_roles.add(role)
    current.hosts = merged
    if not current.networks:
        current.networks = [Network(id="dmz", zone="dmz"), Network(id="int", zone="internal")]
    existing_hops = current.paths[0].hops if current.paths else []
    extras = list(current.paths[1:]) if current.extra_paths_accepted else []
    current.paths = [_primary_path(current.hosts, hops, existing_hops), *extras]
    current.catalog_ids = [h.id for h in current.hosts]
    return current


def run_planner(spec: LabSpec, *, fill: str = "floor") -> LabSpec:
    """Catalog-fill the spec, then refine it with the planner agent when a model is configured.

    ``fill`` is ``floor`` (beginner bar), ``step`` (one hop/host toward the difficulty bar),
    or anything else (the full difficulty minimum). User mode does not invent issues.
    """
    current = spec.model_copy(deep=True)
    if not current.research.opted_in:
        current.research.notes = []
        current.research.citations = []
    if current.vuln_mode == VulnMode.user:
        return current
    if current.difficulty == Difficulty.user_defined:
        current.difficulty = Difficulty.beginner
    key = current.difficulty.value
    min_hosts, min_hops = DIFFICULTY_MINIMA.get(key, (FLOOR_HOSTS, FLOOR_HOPS))
    if fill == "floor":
        target_hosts, target_hops = FLOOR_HOSTS, FLOOR_HOPS
    elif fill == "step":
        have = max(len(current.hosts), FLOOR_HOSTS)
        hops_have = max(len(current.paths[0].hops) - 1, FLOOR_HOPS) if current.paths else FLOOR_HOPS
        target_hosts = min(have + 1, min_hosts)
        target_hops = min(hops_have + 1, min_hops)
        target_hosts = max(target_hosts, target_hops + 1)
    else:
        target_hosts, target_hops = min_hosts, min_hops
        target_hosts = max(target_hosts, target_hops + 1)
    target_hosts = max(target_hosts, len(current.hosts))
    emit(f"Planner: filling {target_hosts} hosts / {target_hops} hops (heuristic catalog).")
    filled = fill_to(current, hosts=target_hosts, hops=target_hops)
    if live_llm_enabled():
        emit("Planner: airouter is refining the plan (this can take a minute).")
        from homelab_creator.workers.agents import refine_plan_with_agent

        return refine_plan_with_agent(filled)
    return filled
