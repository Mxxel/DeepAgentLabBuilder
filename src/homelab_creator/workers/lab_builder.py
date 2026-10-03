"""Lab builder: catalog → session compose + topology after file-write HITL."""

from __future__ import annotations

from pathlib import Path

from langgraph.types import interrupt

from homelab_creator.catalog.render import ALLOWED_IMAGES, render_lab
from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.graph.session import mkdir_session_child, persist_spec, write_session_file
from homelab_creator.spec.models import LabSpec
from homelab_creator.spec.validators import isolation_errors, is_plan_ready
from homelab_creator.workers.invoke import WorkerOutcome

COMPOSE_REL = "compose/docker-compose.yml"
TOPO_REL = "topology.md"
ALLOWED_RELS = frozenset({COMPOSE_REL, TOPO_REL})
WRITE_MAX_BYTES = 64_000
_HITL_ALLOWED = ["approve", "edit", "reject"]


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


def _hitl_files(files: dict[str, str]) -> dict[str, str] | None:
    prompt = _write_prompt(files)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action == "reject":
            return None
        if action == "approve":
            error = _compose_policy_error(files.get(COMPOSE_REL, ""))
            if error:
                prompt = _write_prompt(files, error)
                continue
            return files
        if action == "edit":
            args = value.get("args") if isinstance(value, dict) else None
            edited = args.get("files") if isinstance(args, dict) else None
            if isinstance(edited, dict) and edited:
                cleaned, error = _sanitize_files(edited)
                if error is None:
                    return cleaned
                prompt = _write_prompt(files, error)
                continue
            prompt = _write_prompt(files, "bad_files")
            continue
        prompt = _write_prompt(files, "unknown_action")


def _compose_policy_error(compose: str) -> str | None:
    if isolation_errors(compose):
        return "isolation"
    for raw in compose.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("image:"):
            image = line.split(":", 1)[1].strip().strip("'\"")
            if image not in ALLOWED_IMAGES:
                return "non_catalog_image"
    return None


def _sanitize_files(raw: dict) -> tuple[dict[str, str] | None, str | None]:
    cleaned: dict[str, str] = {}
    for key, text in raw.items():
        if not isinstance(key, str) or not isinstance(text, str):
            return None, "bad_files"
        rel = key.replace("\\", "/").strip().lstrip("./")
        if rel not in ALLOWED_RELS:
            return None, "bad_files"
        if len(text.encode("utf-8")) > WRITE_MAX_BYTES:
            return None, "bad_files"
        cleaned[rel] = text
    if COMPOSE_REL not in cleaned or TOPO_REL not in cleaned:
        return None, "bad_files"
    policy = _compose_policy_error(cleaned[COMPOSE_REL])
    if policy:
        return None, policy
    return cleaned, None


def run_lab_builder(spec: LabSpec, *, session: Path) -> LabSpec | WorkerOutcome:
    """Render catalog compose and topology, then write them after file-write approval.

    Returns ``WorkerOutcome.skip`` when the spec is not plan-ready or the operator rejects the write.
    """
    from homelab_creator.tui.progress import emit

    emit("Lab builder: rendering catalog compose and topology.")
    current = spec.model_copy(deep=True)
    if not is_plan_ready(current):
        return WorkerOutcome.skip
    files = render_lab(current)
    decided = _hitl_files(files)
    if decided is None:
        return WorkerOutcome.skip
    compose_dir = mkdir_session_child(session, "compose")
    write_session_file(compose_dir / "docker-compose.yml", decided[COMPOSE_REL])
    topo = session / "topology.md"
    write_session_file(topo, decided[TOPO_REL])
    current.artifacts.compose_dir = str(compose_dir)
    current.artifacts.topology_path = str(topo)
    current.catalog_ids = [h.id for h in current.hosts]
    persist_spec(session, current)
    return current
