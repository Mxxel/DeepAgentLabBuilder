"""Format interrupt envelopes for the TUI. Does not invent resume protocols."""

from __future__ import annotations

from typing import Any

from homelab_creator.spec.safety import contains_poc

BANNER = "Pwn the company — isolated assessment lab (no exploit recipes in this TUI)."


def _safe(text: object) -> str:
    raw = str(text)
    if contains_poc(raw):
        return "[redacted]"
    return raw


FILE_PREVIEW = 1600

# Shown on combined_form so the TUI is usable without reading the design pack.
FORM_FIELD_HELP = (
    (
        "vuln_mode",
        "user | agent | both",
        "Who authors lab issues: you list them, the planner invents them from catalog roles, or both (your list kept; planner fills the rest).",
    ),
    (
        "difficulty",
        "beginner | intermediate | advanced | senior_expert",
        "Lab size when the planner invents issues (host/hop minima). Required for agent/both; ignored when vuln_mode=user.",
    ),
    (
        "research.opted_in",
        "true | false",
        "If true, you approve a query then Tavily search (search.api_key) plus airouter notes. Default false.",
    ),
    (
        "user_vulns",
        "name|name|…",
        "Issue names you want on the lab, pipe-separated. Names only — never paste exploit recipes. Used when vuln_mode is user or both.",
    ),
)


def render(payload: dict[str, Any], *, hosts: list[dict] | None = None) -> str:
    """Plain-text view of one interrupt. Switches on ``interrupt_kind`` and redacts deny-listed text."""
    kind = str(payload.get("interrupt_kind") or "unknown")
    lines = [BANNER, "", f"[{kind}]"]
    error = payload.get("error")
    if error:
        lines.append(f"error: {_safe(error)}")
    detail = payload.get("detail")
    if detail:
        lines.append(f"detail: {_safe(detail)}")
    allowed = payload.get("allowed") or payload.get("allowed_decisions") or []
    if allowed:
        lines.append("actions: " + ", ".join(_safe(a) for a in allowed))
    if kind == "offer_idea":
        for i, idea in enumerate(payload.get("suggestions") or []):
            lines.append(f"  {i}. {_safe(idea)}")
    if kind == "combined_form":
        lines.append("Type key=value pairs (space or comma). Empty input submits agent + beginner, no research.")
        lines.append("example: vuln_mode=both difficulty=intermediate research.opted_in=false user_vulns=phish-landing|legacy-share")
        fields = payload.get("fields") or []
        help_by_name = {name: (values, blurb) for name, values, blurb in FORM_FIELD_HELP}
        names = list(fields) if fields else [row[0] for row in FORM_FIELD_HELP]
        for name in names:
            values, blurb = help_by_name.get(str(name), ("", ""))
            label = _safe(name)
            if values:
                lines.append(f"  {label}  {values}")
            else:
                lines.append(f"  {label}")
            if blurb:
                lines.append(f"    {_safe(blurb)}")
    if kind == "extend_chain":
        for err in payload.get("errors") or []:
            lines.append(f"  - {_safe(err)}")
    if kind == "hitl_tool":
        lines.append(f"tool: {_safe(payload.get('tool'))}")
        if payload.get("tool") == "search" and payload.get("error") == "missing_key":
            lines.append("No Tavily key. Set search.api_key in conf.yaml (or TAVILY_API_KEY), then retry; or type skip.")
            lines.append("airouter.api_key is the chat model. Tavily is web search.")
        elif payload.get("tool") == "search" and not payload.get("error"):
            lines.append("Approve this public-writeup query (approve / reject / edit:…).")
            lines.append("Then Tavily search runs if search.api_key is set; airouter refines finding classes.")
        args = payload.get("args") or {}
        if isinstance(args, dict):
            if payload.get("tool") == "write_session_files":
                files = args.get("files") or {}
                if isinstance(files, dict):
                    lines.append("files: " + ", ".join(_safe(name) for name in files))
                    for name, body in files.items():
                        text = _safe(body)
                        if len(text) > FILE_PREVIEW:
                            text = text[:FILE_PREVIEW] + "\n…[truncated]"
                        lines.append(f"----- { _safe(name) } -----")
                        lines.append(text)
            else:
                for key, value in args.items():
                    if key == "files":
                        continue
                    lines.append(f"  {key}={_safe(value)}")
    if kind == "worker_budget":
        lines.append("retry this worker, skip it, or go to ask_stop")
    table = hosts or payload.get("hosts")
    if isinstance(table, list) and table:
        lines.append("")
        lines.append("hosts:")
        for host in table:
            if not isinstance(host, dict):
                continue
            hid = _safe(host.get("id"))
            role = _safe(host.get("role"))
            lines.append(f"  {hid} ({role})")
    return "\n".join(lines) + "\n"
