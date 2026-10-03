"""Instantiate catalog roles into isolated Compose YAML and topology markdown."""

from __future__ import annotations

from homelab_creator.spec.models import CATALOG_ROLES, EXTRA_ROLES, REQUIRED_ROLES, Host, LabSpec
from homelab_creator.spec.validators import HOST_ID_RE

ROLE_IMAGES: dict[str, str] = {
    "foothold": "nginx:1.27.3-alpine",
    "internal": "httpd:2.4.62-alpine",
    "crown_jewel": "alpine:3.20.3",
    "workstation": "alpine:3.20.3",
    "mail": "alpine:3.20.3",
    "jump": "alpine:3.20.3",
}
ALLOWED_IMAGES = frozenset(ROLE_IMAGES.values())
ROLE_CONTAINER_PORT = {
    "foothold": 80,
    "internal": 80,
    "crown_jewel": 445,
    "workstation": 22,
    "mail": 25,
    "jump": 22,
}
if set(ROLE_IMAGES) != set(CATALOG_ROLES) or set(ROLE_CONTAINER_PORT) != set(CATALOG_ROLES):
    raise RuntimeError("catalog role maps must match CATALOG_ROLES")

KNOWN_SUBNETS = {
    "dmz": ("172.30.10.0/24", 10),
    "int": ("172.30.20.0/24", 20),
}
EXTRA_SUBNET_OCTET = 30


def _networks_for(host: Host) -> list[str]:
    if host.networks:
        return list(host.networks)
    return ["dmz"] if host.role == "foothold" else ["int"]


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_id(value: str) -> str:
    if HOST_ID_RE.fullmatch(value):
        return value
    return _yaml_quote(value)


def _ordered_nets(spec: LabSpec) -> list[str]:
    used: list[str] = []
    for host in spec.hosts:
        for net in _networks_for(host):
            if net not in used:
                used.append(net)
    for net in spec.networks:
        if net.id not in used:
            used.append(net.id)
    return used or ["dmz", "int"]


def _subnet_for(net: str, extra_index: int) -> tuple[str, int]:
    if net in KNOWN_SUBNETS:
        prefix, third = KNOWN_SUBNETS[net]
        return prefix, third
    third = EXTRA_SUBNET_OCTET + extra_index
    return f"172.30.{third}.0/24", third


def assign_host_ips(spec: LabSpec) -> dict[str, dict[str, str]]:
    """host id → {network id → ipv4}."""
    nets = _ordered_nets(spec)
    extra_i = 0
    thirds: dict[str, int] = {}
    for net in nets:
        if net in KNOWN_SUBNETS:
            thirds[net] = KNOWN_SUBNETS[net][1]
        else:
            _, third = _subnet_for(net, extra_i)
            thirds[net] = third
            extra_i += 1
    next_host = {net: 10 for net in nets}
    assigned: dict[str, dict[str, str]] = {}
    for host in spec.hosts:
        addrs: dict[str, str] = {}
        for net in _networks_for(host):
            octet = next_host[net]
            if octet > 254:
                raise ValueError(f"too many hosts on network {net}")
            next_host[net] = octet + 1
            addrs[net] = f"172.30.{thirds[net]}.{octet}"
        assigned[host.id] = addrs
    return assigned


def render_compose(spec: LabSpec) -> str:
    """Compose YAML: catalog images, bridge networks, and static IPv4. No host port publishes."""
    nets = _ordered_nets(spec)
    ips = assign_host_ips(spec)
    extra_i = 0
    net_meta: dict[str, str] = {}
    for net in nets:
        prefix, _ = _subnet_for(net, extra_i)
        if net not in KNOWN_SUBNETS:
            extra_i += 1
        net_meta[net] = prefix
    lines = ["services:"]
    for host in spec.hosts:
        image = ROLE_IMAGES[host.role]
        host_nets = _networks_for(host)
        port = ROLE_CONTAINER_PORT[host.role]
        lines.append(f"  {_yaml_id(host.id)}:")
        lines.append(f"    image: {image}")
        lines.append(f"    expose: [{port}]")
        lines.append("    networks:")
        for net in host_nets:
            lines.append(f"      {_yaml_id(net)}:")
            lines.append(f"        ipv4_address: {ips[host.id][net]}")
        if host.vulns:
            seed = ",".join(host.vulns)
            lines.append("    environment:")
            lines.append(f"      LAB_VULN_CLASS: {_yaml_quote(seed)}")
    lines.append("networks:")
    for net in nets:
        prefix = net_meta[net]
        gateway = prefix.rsplit(".", 1)[0] + ".1"
        lines.append(f"  {_yaml_id(net)}:")
        lines.append("    driver: bridge")
        lines.append("    ipam:")
        lines.append("      config:")
        lines.append(f"        - subnet: {prefix}")
        lines.append(f"          gateway: {gateway}")
    return "\n".join(lines) + "\n"


def render_topology(spec: LabSpec) -> str:
    """Markdown inventory of networks, hosts, addresses, stacks, issues, and paths."""
    ips = assign_host_ips(spec)
    lines = ["# Topology", "", spec.idea.strip() or "company lab", "", "## Networks"]
    for net in _ordered_nets(spec):
        lines.append(f"- {net}")
    lines.append("")
    lines.append("## Hosts")
    for host in spec.hosts:
        addrs = ips.get(host.id, {})
        ip_note = ", ".join(f"{net}={ip}" for net, ip in addrs.items())
        lines.append(f"### {host.id} ({host.role})")
        lines.append(f"- stack: {', '.join(host.stack) or host.role}")
        lines.append(f"- vulns: {', '.join(host.vulns)}")
        lines.append(f"- networks: {', '.join(_networks_for(host))}")
        lines.append(f"- ipv4: {ip_note}")
        lines.append("")
    lines.append("## Paths")
    for path in spec.paths:
        lines.append(f"- {' -> '.join(path.hops)}")
    catalog = spec.catalog_ids or [h.id for h in spec.hosts]
    lines.append("")
    lines.append("## Catalog")
    lines.append(f"- ids: {', '.join(catalog)}")
    lines.append(f"- required: {', '.join(REQUIRED_ROLES)}")
    lines.append(f"- extras: {', '.join(EXTRA_ROLES)}")
    return "\n".join(lines) + "\n"


def render_lab(spec: LabSpec) -> dict[str, str]:
    """Session-relative paths to compose and topology text for the lab builder."""
    return {
        "compose/docker-compose.yml": render_compose(spec),
        "topology.md": render_topology(spec),
    }
