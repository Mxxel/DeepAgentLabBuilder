"""Plan-ready vs artifact-ready checks."""

from __future__ import annotations

import re
from pathlib import Path

from homelab_creator.spec.models import (
    CATALOG_ROLES,
    COMPOSE_FILENAMES,
    DIFFICULTY_MINIMA,
    REQUIRED_ROLES,
    LabSpec,
    VulnMode,
)
import yaml

from homelab_creator.spec.safety import contains_poc

COMPANY_MIN_HOSTS = 2
HOST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")
RESERVED_COMPOSE_IDS = frozenset(
    {
        "ports",
        "published",
        "host_ip",
        "build",
        "privileged",
        "network_mode",
        "volumes",
        "networks",
        "services",
        "expose",
        "image",
    }
)
_HOST_PUBLISH = re.compile(
    r"^-\s*['\"]?(?:\d+:\d+|(?:127\.0\.0\.1|localhost|::1|0\.0\.0\.0|\[::\]):\S+)",
    re.IGNORECASE,
)
_ABS_BIND = re.compile(r"^-\s*['\"]?(?:/|[A-Za-z]:[\\/]|\.\./)")


def compose_file(compose_dir: Path) -> Path | None:
    """First real compose file in ``compose_dir``. Symlinks are skipped."""
    for name in COMPOSE_FILENAMES:
        candidate = compose_dir / name
        if candidate.is_symlink():
            continue
        if candidate.is_file():
            return candidate
    return None


def _load_text(path: str | None) -> str:
    if not path:
        return ""
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        return ""
    return file.read_text(encoding="utf-8")


def _compose_text(spec: LabSpec, override: str | None) -> str:
    if override is not None:
        return override
    directory = spec.artifacts.compose_dir
    if not directory:
        return ""
    found = compose_file(Path(directory))
    if found is None:
        return ""
    return found.read_text(encoding="utf-8")


def _writeup_text(spec: LabSpec, override: str | None) -> str:
    if override is not None:
        return override
    return _load_text(spec.artifacts.writeup_path)


def _host_in_compose(host_id: str, compose_text: str) -> bool:
    return bool(re.search(rf"(?m)^[ \t]*{re.escape(host_id)}:", compose_text))


def host_in_writeup(host_id: str, writeup_text: str) -> bool:
    """True when ``host_id`` appears as its own token, not as part of a longer id."""
    return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(host_id)}(?![A-Za-z0-9_-])", writeup_text))


def plan_ready_errors(spec: LabSpec) -> list[str]:
    """Reasons the spec cannot be built yet. An empty list means plan-ready.

    Host and hop minima apply only when ``vuln_mode`` is ``agent`` or ``both``.
    Extra paths are rejected until ``extra_paths_accepted`` is true.
    """
    errors: list[str] = []
    if spec.objective != "full_network_compromise":
        errors.append("objective must be full_network_compromise")
    if not spec.hosts:
        errors.append("no hosts")
    elif len(spec.hosts) < COMPANY_MIN_HOSTS:
        errors.append("single-service lab is not a company")
    ids = [h.id for h in spec.hosts]
    host_ids = set(ids)
    if len(ids) != len(host_ids):
        errors.append("duplicate host id")
    for host in spec.hosts:
        if not host.id.strip():
            errors.append("empty host id")
        elif not HOST_ID_RE.fullmatch(host.id) or host.id.lower() in RESERVED_COMPOSE_IDS:
            errors.append(f"unsafe host id: {host.id}")
        if host.role not in CATALOG_ROLES:
            errors.append(f"non-catalog role: {host.role}")
        if not host.stack:
            errors.append(f"host {host.id} missing stack")
        if not host.vulns:
            errors.append(f"host {host.id} missing vulns")
        for net in host.networks:
            if net and (not HOST_ID_RE.fullmatch(net) or net.lower() in RESERVED_COMPOSE_IDS):
                errors.append(f"unsafe network id: {net}")
    for net in spec.networks:
        if not HOST_ID_RE.fullmatch(net.id) or net.id.lower() in RESERVED_COMPOSE_IDS:
            errors.append(f"unsafe network id: {net.id}")
    if not spec.paths:
        errors.append("no compromise path")
    for i, path in enumerate(spec.paths):
        if not path.hops:
            errors.append(f"path {i} has no hops")
            continue
        unknown = [hop for hop in path.hops if hop not in host_ids]
        if unknown:
            errors.append(f"path {i} hops not host ids: {', '.join(unknown)}")
    extra_count = max(0, len(spec.paths) - 1)
    if extra_count and not spec.extra_paths_accepted:
        errors.append("extra paths without extra_paths_accepted")
    if spec.vuln_mode in (VulnMode.agent, VulnMode.both):
        key = spec.difficulty.value
        if key in DIFFICULTY_MINIMA:
            min_hosts, min_hops = DIFFICULTY_MINIMA[key]
            if len(spec.hosts) < min_hosts:
                errors.append(f"need at least {min_hosts} hosts for {key}")
            if _primary_hop_edges(spec) < min_hops:
                errors.append(f"need at least {min_hops} hops for {key}")
        roles = {h.role for h in spec.hosts}
        missing = [r for r in REQUIRED_ROLES if r not in roles]
        if missing:
            errors.append(f"missing required roles: {', '.join(missing)}")
    return errors


def is_plan_ready(spec: LabSpec) -> bool:
    """True when the spec may take the first-build or rebuild shortcut."""
    return not plan_ready_errors(spec)


def _primary_hop_edges(spec: LabSpec) -> int:
    if not spec.paths or not spec.paths[0].hops:
        return 0
    return max(0, len(spec.paths[0].hops) - 1)


def path_hops_are_hosts(spec: LabSpec, hops: list[str]) -> bool:
    """True when every hop is a host id already on the spec."""
    if not hops:
        return False
    ids = {h.id for h in spec.hosts}
    return all(hop in ids for hop in hops)


def has_valid_path(spec: LabSpec) -> bool:
    """True when at least one compromise path uses only known host ids."""
    return any(path_hops_are_hosts(spec, path.hops) for path in spec.paths)


def _line_key_value(line: str) -> tuple[str, str] | None:
    stripped = line.split("#", 1)[0].strip().lower().replace('"', "").replace("'", "")
    if ":" not in stripped:
        return None
    key, value = stripped.split(":", 1)
    return key.replace(" ", "").replace("\t", ""), value.replace(" ", "").replace("\t", "")


def _volume_is_host_bind(item: object) -> bool:
    if isinstance(item, dict):
        source = item.get("source") or item.get("Source")
        typ = str(item.get("type") or item.get("Type") or "").strip().lower()
        if typ == "bind":
            return True
        return _volume_is_host_bind(source)
    if not isinstance(item, str):
        return False
    text = item.strip().strip("'\"")
    if text.startswith("-"):
        text = text[1:].strip()
    if "$" in text:
        return True
    return bool(re.match(r"(?:/|[A-Za-z]:[\\/]|\.\./)", text))


_INTERP = re.compile(r"\$\{|\$[A-Za-z_]")
_SENSITIVE = frozenset({"network_mode", "privileged", "build", "ports", "published", "host_ip", "volumes", "type"})


def _has_interp(value: object) -> bool:
    return bool(_INTERP.search(str(value)))


def _walk_isolation(node: object, errors: list[str]) -> None:
    if isinstance(node, dict):
        for raw_key, value in node.items():
            key = str(raw_key).strip().lower()
            if key in _SENSITIVE and _has_interp(value):
                errors.append("compose interpolation forbidden")
            if key == "network_mode" and str(value).strip().lower() == "host":
                errors.append("host network forbidden")
            if key == "privileged" and (value is True or str(value).strip().lower() in {"true", "yes", "on", "1"}):
                errors.append("privileged forbidden")
            if key == "build" and value not in (None, "", False, 0):
                errors.append("compose build forbidden")
            if key in {"ports", "published", "host_ip"}:
                errors.append("host port publish forbidden")
            if key == "type" and str(value).strip().lower() == "bind":
                errors.append("host bind mount forbidden")
            if key == "volumes":
                if isinstance(value, list):
                    for item in value:
                        if _volume_is_host_bind(item):
                            errors.append("host bind mount forbidden")
                elif _volume_is_host_bind(value):
                    errors.append("host bind mount forbidden")
            _walk_isolation(value, errors)
        return
    if isinstance(node, list):
        for item in node:
            _walk_isolation(item, errors)


def isolation_errors(compose_text: str) -> list[str]:
    """Isolation violations: host network, published ports, host binds, privileged, or build."""
    errors: list[str] = []
    for raw in compose_text.splitlines():
        parsed = _line_key_value(raw)
        if parsed is None:
            line = raw.split("#", 1)[0].strip()
            if line.startswith("-"):
                if _HOST_PUBLISH.match(line):
                    errors.append("host port publish forbidden")
                if _ABS_BIND.match(line):
                    errors.append("host bind mount forbidden")
            continue
        key, value = parsed
        if key in _SENSITIVE and _has_interp(value):
            errors.append("compose interpolation forbidden")
        if key == "network_mode" and value == "host":
            errors.append("host network forbidden")
        if key == "privileged" and value in {"true", "yes", "on", "1"}:
            errors.append("privileged forbidden")
        if key == "build":
            errors.append("compose build forbidden")
        if key in {"ports", "published", "host_ip"}:
            errors.append("host port publish forbidden")
        if key == "type" and value == "bind":
            errors.append("host bind mount forbidden")
    try:
        loaded = yaml.safe_load(compose_text) if compose_text.strip() else {}
    except yaml.YAMLError:
        errors.append("compose yaml invalid")
        return errors
    _walk_isolation(loaded, errors)
    return errors


def artifact_ready_errors(
    spec: LabSpec,
    *,
    compose_text: str | None = None,
    writeup_text: str | None = None,
) -> list[str]:
    """Reasons generated files are incomplete or unsafe. An empty list means artifact-ready.

    Pass ``compose_text`` or ``writeup_text`` to check in-memory drafts instead of disk.
    """
    errors: list[str] = []
    compose_dir = spec.artifacts.compose_dir
    compose_path = Path(compose_dir) if compose_dir else None
    if not compose_path or not compose_path.is_dir() or compose_file(compose_path) is None:
        errors.append("compose dir missing")
    topo = spec.artifacts.topology_path
    topo_path = Path(topo) if topo else None
    if not topo_path or topo_path.is_symlink() or not topo_path.is_file():
        errors.append("topology.md missing")
    loaded_topo = _load_text(str(topo_path) if topo_path else "")
    scan_topo = bool(topo_path and not topo_path.is_symlink() and topo_path.is_file())
    writeup = spec.artifacts.writeup_path
    writeup_path = Path(writeup) if writeup else None
    if not writeup_path or writeup_path.is_symlink() or not writeup_path.is_file():
        errors.append("writeup missing")
    loaded_compose = _compose_text(spec, compose_text)
    loaded_writeup = _writeup_text(spec, writeup_text)
    scan_compose = compose_text is not None or (
        compose_path is not None and compose_file(compose_path) is not None
    )
    scan_writeup = writeup_text is not None or (
        writeup_path is not None and not writeup_path.is_symlink() and writeup_path.is_file()
    )
    errors.extend(isolation_errors(loaded_compose))
    for host in spec.hosts:
        if not host.id.strip():
            errors.append("empty host id")
            continue
        if scan_compose and not _host_in_compose(host.id, loaded_compose):
            errors.append(f"host {host.id} missing from compose")
        if scan_topo and not host_in_writeup(host.id, loaded_topo):
            errors.append(f"host {host.id} missing from topology")
        if scan_writeup and not host_in_writeup(host.id, loaded_writeup):
            errors.append(f"host {host.id} missing from writeup")
    if scan_writeup and contains_poc(loaded_writeup):
        errors.append("exploit-PoC language in writeup")
    if scan_writeup and spec.research.opted_in:
        for cite in spec.research.citations:
            if cite.strip() and not contains_poc(cite) and cite.strip() not in loaded_writeup:
                errors.append("citation missing from writeup")
    if scan_writeup and not spec.research.opted_in and re.search(r"(?im)^##\s*citations\s*$", loaded_writeup):
        errors.append("citations present but research skipped")
    return errors


def is_artifact_ready(
    spec: LabSpec,
    *,
    compose_text: str | None = None,
    writeup_text: str | None = None,
) -> bool:
    """True when compose, topology, and writeup match the spec and isolation rules."""
    return not artifact_ready_errors(spec, compose_text=compose_text, writeup_text=writeup_text)
