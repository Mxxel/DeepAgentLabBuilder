"""Writeup worker: inventory, hops, citations only when research ran."""

from __future__ import annotations

import re
from pathlib import Path

from langgraph.types import interrupt

from homelab_creator.catalog.render import assign_host_ips
from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.graph.session import persist_spec, write_session_file
from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.safety import contains_poc
from homelab_creator.spec.validators import host_in_writeup, is_artifact_ready, is_plan_ready
from homelab_creator.workers.invoke import WorkerOutcome

WRITEUP_REL = "writeup.md"
WRITE_MAX_BYTES = 64_000
_HITL_ALLOWED = ["approve", "edit", "reject"]


def render_writeup(spec: LabSpec) -> str:
    """Assessment inventory: hosts, addresses, hops, and citations only if research ran."""
    ips = assign_host_ips(spec)
    lines = [
        "# Writeup",
        "",
        f"Objective: {spec.objective}",
        f"Idea: {spec.idea.strip() or 'company lab'}",
        "",
        "## Inventory",
    ]
    for host in spec.hosts:
        addrs = ips.get(host.id, {})
        ip_note = ", ".join(f"{net}={ip}" for net, ip in addrs.items())
        vulns = [v for v in host.vulns if not contains_poc(v)]
        lines.append(f"### {host.id} ({host.role})")
        lines.append(f"- stack: {', '.join(host.stack) or host.role}")
        lines.append(f"- findings: {', '.join(vulns)}")
        if ip_note:
            lines.append(f"- ipv4: {ip_note}")
        lines.append("")
    lines.append("## Compromise paths")
    for path in spec.paths:
        lines.append(f"- {' -> '.join(path.hops)}")
    lines.append("")
    if spec.research.opted_in:
        lines.append("## Research")
        for note in spec.research.notes:
            if note.strip() and not contains_poc(note):
                lines.append(f"- {note.strip()}")
        lines.append("")
        lines.append("## Citations")
        for cite in spec.research.citations:
            if cite.strip() and not contains_poc(cite):
                lines.append(f"- {cite.strip()}")
        if not spec.research.citations:
            lines.append("- none recorded")
        lines.append("")
    text = "\n".join(lines) + "\n"
    if contains_poc(text):
        text = text.replace("payload:", "finding:")
    return text


def _write_prompt(files: dict[str, str], error: str | None = None) -> dict:
    payload = envelope(
        "hitl_tool",
        tool="write_session_files",
        args={"files": files},
        allowed_decisions=_HITL_ALLOWED,
        allowed=_HITL_ALLOWED,
    )
    if error:
        payload["error"] = error
    return payload


def _writeup_policy_error(spec: LabSpec, text: str) -> str | None:
    if contains_poc(text):
        return "poc"
    for host in spec.hosts:
        if host.id.strip() and not host_in_writeup(host.id, text):
            return "missing_host"
    if spec.research.opted_in:
        for cite in spec.research.citations:
            if cite.strip() and not contains_poc(cite) and cite.strip() not in text:
                return "missing_citation"
    elif re.search(r"(?im)^##\s*citations\s*$", text):
        return "unexpected_citations"
    return None


def _sanitize_files(spec: LabSpec, raw: dict) -> tuple[dict[str, str] | None, str | None]:
    if WRITEUP_REL not in raw:
        return None, "bad_files"
    cleaned: dict[str, str] = {}
    for key, text in raw.items():
        if not isinstance(key, str) or not isinstance(text, str):
            return None, "bad_files"
        rel = key.replace("\\", "/").strip().lstrip("./")
        if rel != WRITEUP_REL:
            return None, "bad_files"
        if len(text.encode("utf-8")) > WRITE_MAX_BYTES:
            return None, "bad_files"
        cleaned[rel] = text
    policy = _writeup_policy_error(spec, cleaned[WRITEUP_REL])
    if policy:
        return None, policy
    return cleaned, None


def _hitl_writeup(spec: LabSpec, files: dict[str, str]) -> dict[str, str] | None:
    prompt = _write_prompt(files)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action == "reject":
            return None
        if action == "approve":
            error = _writeup_policy_error(spec, files.get(WRITEUP_REL, ""))
            if error:
                prompt = _write_prompt(files, error)
                continue
            return files
        if action == "edit":
            args = value.get("args") if isinstance(value, dict) else None
            edited = args.get("files") if isinstance(args, dict) else None
            if isinstance(edited, dict) and edited:
                cleaned, error = _sanitize_files(spec, edited)
                if error is None:
                    return cleaned
                prompt = _write_prompt(files, error)
                continue
            prompt = _write_prompt(files, "bad_files")
            continue
        prompt = _write_prompt(files, "unknown_action")


def run_writeup(spec: LabSpec, *, session: Path) -> LabSpec | WorkerOutcome:
    """Write ``writeup.md`` after approval and record whether the artifact set is still stale."""
    from homelab_creator.tui.progress import emit

    emit("Writeup: drafting assessment inventory (no exploit recipes).")
    current = spec.model_copy(deep=True)
    if not is_plan_ready(current):
        return WorkerOutcome.skip
    files = {WRITEUP_REL: render_writeup(current)}
    decided = _hitl_writeup(current, files)
    if decided is None:
        return WorkerOutcome.skip
    path = session / "writeup.md"
    write_session_file(path, decided[WRITEUP_REL])
    current.artifacts.writeup_path = str(path)
    persist_spec(session, current)
    current.artifacts_stale = not is_artifact_ready(current)
    return current
