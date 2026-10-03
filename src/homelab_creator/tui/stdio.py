"""Stdlib interactive TUI: print render(payload) and read a resume value."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homelab_creator.tui.render import render


class StdioTUI:
    """Line-input TUI selected by ``--plain``. Prints ``render(payload)`` and reads a resume."""

    def __init__(
        self,
        *,
        read: Callable[[], str] | None = None,
        write: Callable[[str], None] | None = None,
    ) -> None:
        self._read = read or (lambda: input("> "))
        self._write = write or (lambda text: print(text, end=""))

    def progress(self, message: str) -> None:
        self._write(f"[progress] {message}\n")

    def show(self, payload: dict[str, Any], *, hosts: list[dict] | None = None) -> Any:
        self._write(render(payload, hosts=hosts))
        try:
            raw = self._read().strip()
        except EOFError:
            return "stop"
        kind = payload.get("interrupt_kind")
        if kind == "combined_form":
            return _parse_form(raw)
        if kind == "offer_idea" and raw.startswith("pick="):
            try:
                return {"pick": int(raw.split("=", 1)[1])}
            except ValueError:
                return raw
        if kind == "hitl_tool" and raw.startswith("edit:"):
            rest = raw.split(":", 1)[1].strip()
            tool = payload.get("tool")
            if tool == "compose_cli":
                return raw
            if tool == "write_session_files":
                if "::" in rest:
                    name, body = rest.split("::", 1)
                    rel = name.strip().replace("\\", "/").lstrip("./")
                    return {"action": "edit", "args": {"files": {rel: body.replace("\\n", "\n")}}}
                return {"action": "edit", "args": {"error": "need edit:path::body"}}
            return {"action": "edit", "args": {"query": rest}}
        return raw


def _parse_form(raw: str) -> dict[str, Any]:
    if raw in {"submit", ""}:
        return {"action": "submit", "vuln_mode": "agent", "difficulty": "beginner", "research.opted_in": False}
    fields: dict[str, Any] = {"action": "submit"}
    for part in raw.replace(",", " ").split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key == "research.opted_in":
            fields[key] = value.lower()
        elif key == "user_vulns":
            fields[key] = [v for v in value.split("|") if v]
        else:
            fields[key] = value
    if "vuln_mode" not in fields:
        fields["vuln_mode"] = "agent"
    if fields.get("vuln_mode") != "user" and "difficulty" not in fields:
        fields["difficulty"] = "beginner"
    if "research.opted_in" not in fields:
        fields["research.opted_in"] = False
    return fields
