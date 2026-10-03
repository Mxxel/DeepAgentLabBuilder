"""Interview and lab graph nodes (form, workers, extra-path, compose HITL)."""

from __future__ import annotations

from typing import Literal

from langgraph.types import Command, interrupt
from pydantic import ValidationError

from langchain_core.runnables import RunnableConfig

from homelab_creator.graph.envelope import envelope, resume_action
from homelab_creator.graph.session import persist_spec, resolve_session_dir
from homelab_creator.graph.state import GraphState, dump_spec
from homelab_creator.tui.progress import emit
from homelab_creator.spec.models import CompromisePath, Difficulty, Host, LabSpec, LabUpStatus, VulnMode
from homelab_creator.spec.validators import HOST_ID_RE, compose_file, is_artifact_ready, is_plan_ready, plan_ready_errors
from homelab_creator.tools.compose_cli import run_compose
from homelab_creator.workers.invoke import WorkerOutcome, invoke_worker, unwrap_worker
from homelab_creator.workers.lab_builder import run_lab_builder
from homelab_creator.workers.planner import run_planner
from homelab_creator.workers.research import run_research
from homelab_creator.workers.writeup import run_writeup


def _spec(state: GraphState) -> LabSpec:
    return LabSpec.model_validate(state.get("spec") or {})


def compose_exists(state: GraphState) -> bool:
    """True when the session has a real compose file. Symlink compose dirs do not count."""
    try:
        session = resolve_session_dir(state)
    except ValueError:
        return False
    directory = session / "compose"
    return directory.is_dir() and not directory.is_symlink() and compose_file(directory) is not None


FORM_FIELDS = ["vuln_mode", "difficulty", "research.opted_in", "user_vulns"]
USER_VULN_MAX_COUNT = 32
USER_VULN_MAX_LEN = 200
ADD_HOPS_MAX_HOSTS = 32
ADD_HOPS_MAX_HOPS = 32
_TRUE = {True, "true"}
_FALSE = {False, "false"}


def combined_form(state: GraphState) -> Command:
    """Record vuln mode, difficulty, research, and user issues, then start research or planning.

    There is no ``ask_stop`` between this resume and the worker batch.
    """
    prompt = envelope("combined_form", allowed=["submit"], fields=FORM_FIELDS)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action != "submit" or not isinstance(value, dict):
            prompt = envelope(
                "combined_form",
                allowed=["submit"],
                fields=FORM_FIELDS,
                error="unknown_action",
            )
            continue
        spec = _spec(state)
        patched, error = _apply_form_patch(spec, value)
        if error:
            prompt = envelope(
                "combined_form",
                allowed=["submit"],
                fields=FORM_FIELDS,
                error=error,
            )
            continue
        spec = patched
        break
    spec.form_completed = True
    spec.idea_locked = True
    spec.extra_paths_accepted = False
    dest = "research_worker" if spec.research.opted_in else "vuln_planner"
    notes: list[str] = []
    if dest == "vuln_planner":
        spec.research.notes = []
        spec.research.citations = []
    return Command(
        update={
            "spec": dump_spec(spec),
            "interrupt_kind": dest,
            "planner_input_notes": notes,
            "agent_auto_replan_done": False,
        },
        goto=dest,
    )


def _parse_opted_in(value: dict) -> tuple[bool | None, str | None]:
    raw: object
    research = value.get("research")
    if isinstance(research, dict) and "opted_in" in research:
        raw = research["opted_in"]
    elif "research.opted_in" in value:
        raw = value["research.opted_in"]
    elif "research_opted_in" in value:
        raw = value["research_opted_in"]
    else:
        return False, None
    if isinstance(raw, str):
        raw = raw.strip().lower()
    if raw in _TRUE:
        return True, None
    if raw in _FALSE:
        return False, None
    return None, "bad_research_opted_in"


def _parse_user_vulns(raw: object) -> tuple[list[str] | None, str | None]:
    if not isinstance(raw, list):
        return None, "bad_user_vulns"
    if len(raw) > USER_VULN_MAX_COUNT:
        return None, "bad_user_vulns"
    cleaned: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None, "bad_user_vulns"
        text = item.strip()
        if not text:
            continue
        if len(text) > USER_VULN_MAX_LEN:
            return None, "bad_user_vulns"
        cleaned.append(text)
    return cleaned, None


def _apply_form_patch(spec: LabSpec, value: dict) -> tuple[LabSpec, str | None]:
    current = spec.model_copy(deep=True)
    mode_raw = value.get("vuln_mode")
    try:
        current.vuln_mode = VulnMode(mode_raw)
    except ValueError:
        return spec, "bad_vuln_mode"
    if current.vuln_mode == VulnMode.user:
        current.difficulty = Difficulty.user_defined
    else:
        try:
            current.difficulty = Difficulty(value.get("difficulty"))
        except ValueError:
            return spec, "bad_difficulty"
        if current.difficulty == Difficulty.user_defined:
            return spec, "bad_difficulty"
    opted, error = _parse_opted_in(value)
    if error:
        return spec, error
    current.research.opted_in = bool(opted)
    if "user_vulns" in value:
        vulns, error = _parse_user_vulns(value["user_vulns"])
        if error:
            return spec, error
        current.user_vulns = vulns or []
    return current, None


def research_worker(state: GraphState, config: RunnableConfig) -> Command:
    """Run research through the worker wrapper, then hand notes to the planner.

    ``configurable['search']`` replaces the Tavily backend in tests.
    """
    spec = _spec(state)
    emit("Research worker started. Waiting for query approve, then Tavily/model notes.")
    search = (config.get("configurable") or {}).get("search")
    result = invoke_worker(run_research, spec, search=search)
    spec, outcome = unwrap_worker(result, spec)
    if outcome is WorkerOutcome.ask_stop:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    if outcome is WorkerOutcome.skip:
        spec.research.notes = []
        spec.research.citations = []
    notes = list(spec.research.notes) if spec.research.opted_in else []
    return Command(
        update={
            "spec": dump_spec(spec),
            "planner_input_notes": notes,
            "interrupt_kind": "vuln_planner",
        },
        goto="vuln_planner",
    )


def vuln_planner(state: GraphState) -> Command:
    """Fill a catalog plan. Agent and both modes get one automatic replan if not plan-ready."""
    spec = _spec(state)
    emit("Planner started: filling catalog roles and the pwn-the-company path.")
    result = invoke_worker(run_planner, spec, fill="floor")
    spec, outcome = unwrap_worker(result, spec)
    if outcome is WorkerOutcome.ask_stop:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    auto_done = bool(state.get("agent_auto_replan_done"))
    if (
        not is_plan_ready(spec)
        and spec.vuln_mode in (VulnMode.agent, VulnMode.both)
        and not auto_done
    ):
        result = invoke_worker(run_planner, spec, fill="step")
        spec, outcome = unwrap_worker(result, spec)
        auto_done = True
        if outcome is WorkerOutcome.ask_stop:
            return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop", "agent_auto_replan_done": True}, goto="ask_stop")
    notes = list(spec.research.notes) if spec.research.opted_in else []
    dest = "ask_extra_paths" if is_plan_ready(spec) else "extend_chain"
    return Command(
        update={
            "spec": dump_spec(spec),
            "planner_input_notes": notes,
            "validation_errors": plan_ready_errors(spec),
            "interrupt_kind": dest,
            "agent_auto_replan_done": auto_done,
        },
        goto=dest,
    )


def _extend_allowed(spec: LabSpec) -> list[str]:
    if spec.vuln_mode == VulnMode.user:
        return ["switch_to_both", "add_hops", "abandon_generation"]
    return ["replan", "add_hops", "abandon_generation"]


def _valid_host_id(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not HOST_ID_RE.fullmatch(text):
        return None
    return text


def _apply_add_hops(spec: LabSpec, value: object) -> tuple[LabSpec, str | None]:
    current = spec.model_copy(deep=True)
    if not isinstance(value, dict):
        return spec, "bad_hosts"
    hosts_raw = value.get("hosts")
    if hosts_raw is not None:
        if not isinstance(hosts_raw, list) or len(hosts_raw) > ADD_HOPS_MAX_HOSTS:
            return spec, "bad_hosts"
        parsed: list[Host] = []
        seen: set[str] = set()
        for item in hosts_raw:
            if not isinstance(item, dict):
                return spec, "bad_hosts"
            try:
                host = Host.model_validate(item)
            except ValidationError:
                return spec, "bad_hosts"
            if not _valid_host_id(host.id):
                return spec, "bad_hosts"
            if host.id in seen:
                return spec, "bad_hosts"
            seen.add(host.id)
            parsed.append(host)
        if parsed:
            current.hosts = parsed
    hops = value.get("hops")
    if hops is not None:
        if not isinstance(hops, list) or not hops or len(hops) > ADD_HOPS_MAX_HOPS:
            return spec, "bad_hops"
        cleaned_hops: list[str] = []
        for hop in hops:
            hid = _valid_host_id(hop)
            if hid is None:
                return spec, "bad_hops"
            cleaned_hops.append(hid)
        current.paths = [CompromisePath(hops=cleaned_hops)]
        known = {h.id for h in current.hosts}
        if any(hop not in known for hop in cleaned_hops):
            return spec, "bad_hops"
    if "vulns" in value:
        vulns, error = _parse_user_vulns(value["vulns"])
        if error:
            return spec, "bad_user_vulns"
        current.user_vulns = vulns or []
    return current, None


def _apply_switch_to_both(spec: LabSpec, value: object) -> tuple[LabSpec, str | None]:
    current = spec.model_copy(deep=True)
    current.vuln_mode = VulnMode.both
    raw = value.get("difficulty") if isinstance(value, dict) else None
    if raw is None:
        current.difficulty = Difficulty.beginner
        return current, None
    try:
        difficulty = Difficulty(raw)
    except ValueError:
        return spec, "bad_difficulty"
    if difficulty == Difficulty.user_defined:
        return spec, "bad_difficulty"
    current.difficulty = difficulty
    return current, None


def extend_chain(state: GraphState) -> Command:
    """Interrupt while the plan is invalid. This loop does not offer stop or END."""
    spec = _spec(state)
    allowed = _extend_allowed(spec)
    errors = plan_ready_errors(spec)
    prompt = envelope("extend_chain", allowed=allowed, errors=errors)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action not in allowed:
            prompt = envelope("extend_chain", allowed=allowed, errors=errors, error="unknown_action")
            continue
        if action == "abandon_generation":
            return Command(update={"spec": dump_spec(spec), "interrupt_kind": "choose_next_move"}, goto="choose_next_move")
        if action == "switch_to_both":
            patched, error = _apply_switch_to_both(spec, value)
            if error:
                prompt = envelope("extend_chain", allowed=allowed, errors=errors, error=error)
                continue
            spec = patched
            fill = "minima"
            break
        if action == "replan":
            fill = "minima"
            break
        patched, error = _apply_add_hops(spec, value)
        if error:
            prompt = envelope("extend_chain", allowed=allowed, errors=errors, error=error)
            continue
        spec = patched
        spec.catalog_ids = [h.id for h in spec.hosts]
        if spec.vuln_mode == VulnMode.user:
            if compose_exists(state):
                spec.artifacts_stale = True
            notes = list(spec.research.notes) if spec.research.opted_in else []
            dest = "ask_extra_paths" if is_plan_ready(spec) else "extend_chain"
            return Command(
                update={
                    "spec": dump_spec(spec),
                    "planner_input_notes": notes,
                    "validation_errors": plan_ready_errors(spec),
                    "interrupt_kind": dest,
                },
                goto=dest,
            )
        fill = "minima"
        break
    result = invoke_worker(run_planner, spec, fill=fill)
    spec, outcome = unwrap_worker(result, spec)
    if outcome is WorkerOutcome.ask_stop:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    dest = "ask_extra_paths" if is_plan_ready(spec) else "extend_chain"
    notes = list(spec.research.notes) if spec.research.opted_in else []
    if compose_exists(state):
        spec.artifacts_stale = True
    return Command(
        update={
            "spec": dump_spec(spec),
            "planner_input_notes": notes,
            "validation_errors": plan_ready_errors(spec),
            "interrupt_kind": dest,
        },
        goto=dest,
    )


def ask_extra_paths(state: GraphState) -> Command[Literal["ask_stop"]]:
    """Ask whether to keep a second compromise path, then go to ``ask_stop``."""
    prompt = envelope("ask_extra_paths", allowed=["yes", "no"])
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in ("yes", "no"):
            break
        prompt = envelope("ask_extra_paths", allowed=["yes", "no"], error="unknown_action")
    spec = _spec(state)
    if action == "yes":
        spec.extra_paths_accepted = True
        if spec.paths:
            hops = spec.paths[0].hops
            alt = list(reversed(hops)) if len(hops) >= 3 else ([hops[0], hops[-1]] if len(hops) > 1 else list(hops))
            if alt and alt != hops and all(p.hops != alt for p in spec.paths):
                spec.paths.append(CompromisePath(hops=alt))
        if compose_exists(state):
            spec.artifacts_stale = True
    return Command(update={"spec": dump_spec(spec)}, goto="ask_stop")


def lab_builder(state: GraphState) -> Command:
    """Render compose and topology after file-write approval, then start the writeup.

    Skip or ask-stop leaves the batch so writeup and lab-up do not run without compose.
    """
    spec = _spec(state)
    emit("Lab builder started: rendering compose + topology for HITL write.")
    session = resolve_session_dir(state)
    result = invoke_worker(run_lab_builder, spec, session=session)
    spec, outcome = unwrap_worker(result, spec)
    if outcome is WorkerOutcome.ask_stop:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    if outcome is WorkerOutcome.skip:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    persist_spec(session, spec)
    return Command(update={"spec": dump_spec(spec)}, goto="writeup_writer")


def writeup_writer(state: GraphState) -> Command:
    """Write the assessment writeup. ``lab_up`` runs only when the artifacts are ready."""
    spec = _spec(state)
    emit("Writeup started: assessment inventory only (no exploit recipes).")
    session = resolve_session_dir(state)
    result = invoke_worker(run_writeup, spec, session=session)
    spec, outcome = unwrap_worker(result, spec)
    if outcome is WorkerOutcome.ask_stop:
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    if outcome is WorkerOutcome.skip:
        if compose_exists(state):
            spec.artifacts_stale = True
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    if not is_artifact_ready(spec):
        spec.artifacts_stale = True
        return Command(update={"spec": dump_spec(spec), "interrupt_kind": "ask_stop"}, goto="ask_stop")
    return Command(update={"spec": dump_spec(spec)}, goto="lab_up")


def lab_up(state: GraphState, config: RunnableConfig) -> Command[Literal["ask_stop"]]:
    """Approve compose up or down, or record an explicit skip, then return to ``ask_stop``.

    ``configurable['compose_cli']`` replaces the Docker runner in tests.
    """
    spec = _spec(state)
    allowed = ["up", "skip"]
    if spec.lab_up_status == LabUpStatus.running:
        allowed.append("down")
    prompt = envelope("lab_up", allowed=allowed)
    while True:
        value = interrupt(prompt)
        action = resume_action(value) or (value if isinstance(value, str) else "")
        if action in allowed:
            break
        prompt = envelope("lab_up", allowed=allowed, error="unknown_action")
    if action == "skip":
        spec.lab_up_status = LabUpStatus.skipped
        return Command(update={"spec": dump_spec(spec), "lab_up_detail": ""}, goto="ask_stop")
    compose_action = action
    detail = ""
    try:
        session = resolve_session_dir(state)
        compose_dir = session / "compose"
    except ValueError as exc:
        spec.lab_up_status = LabUpStatus.failed
        return Command(update={"spec": dump_spec(spec), "lab_up_detail": str(exc)}, goto="ask_stop")
    if compose_dir.is_symlink() or not compose_dir.is_dir() or compose_file(compose_dir) is None:
        spec.lab_up_status = LabUpStatus.failed
        return Command(update={"spec": dump_spec(spec), "lab_up_detail": "compose dir missing"}, goto="ask_stop")
    decided = _hitl_compose(compose_action, compose_dir)
    if decided is None:
        spec.lab_up_status = LabUpStatus.failed
        return Command(update={"spec": dump_spec(spec), "lab_up_detail": "compose HITL rejected"}, goto="ask_stop")
    runner = (config.get("configurable") or {}).get("compose_cli")
    try:
        code, output = run_compose(compose_dir, decided, session=session, runner=runner)
    except ValueError as exc:
        spec.lab_up_status = LabUpStatus.failed
        return Command(update={"spec": dump_spec(spec), "lab_up_detail": str(exc)}, goto="ask_stop")
    if code != 0:
        spec.lab_up_status = LabUpStatus.failed
        detail = output or f"compose {decided} failed ({code})"
    elif decided == "up":
        spec.lab_up_status = LabUpStatus.running
        detail = "compose up --detach ok"
    else:
        spec.lab_up_status = LabUpStatus.not_run
        detail = "compose down ok"
    return Command(update={"spec": dump_spec(spec), "lab_up_detail": detail}, goto="ask_stop")


def _hitl_compose(action: str, compose_dir) -> str | None:
    prompt = envelope(
        "hitl_tool",
        tool="compose_cli",
        args={"action": action, "compose_dir": str(compose_dir)},
        allowed_decisions=["approve", "reject"],
        allowed=["approve", "reject"],
    )
    while True:
        value = interrupt(prompt)
        decision = resume_action(value) or (value if isinstance(value, str) else "")
        if decision == "reject":
            return None
        if decision == "approve":
            return action
        prompt = envelope(
            "hitl_tool",
            tool="compose_cli",
            args={"action": action, "compose_dir": str(compose_dir)},
            allowed=["approve", "reject"],
            allowed_decisions=["approve", "reject"],
            error="unknown_action",
        )
