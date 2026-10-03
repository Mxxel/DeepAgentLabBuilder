"""Interactive TUI: ASCII header + AskUserQuestion-style menus (Rich when available)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from typing import Any

from homelab_creator.tui.brand import ASCII_HEADER, TAGLINE, THEME, header_block
from homelab_creator.tui.menu import AskMenu, MenuOption
from homelab_creator.tui.render import FILE_PREVIEW, _safe
from homelab_creator.tui.stdio import _parse_form

ACTION_HELP: dict[str, str] = {
    "continue": "Keep the interview going",
    "stop": "End this session",
    "more_brainstorm": "Another idea round before locking",
    "lock_idea_and_form": "Lock the idea and open the vuln/research form",
    "redo_form": "Re-open the vuln/research form, then research/plan again",
    "ask_extra_paths": "Add optional extra compromise paths",
    "build": "Generate compose, topology, and writeup",
    "rebuild": "Regenerate compose/topology/writeup (artifacts stale)",
    "lab_up": "Start, skip, or stop the Docker Compose lab",
    "up": "docker compose up --detach (isolated networks)",
    "down": "docker compose down",
    "skip": "Skip this step and continue the interview",
    "yes": "Accept",
    "no": "Decline",
    "approve": "Approve and run",
    "reject": "Reject and skip",
    "edit": "Edit the proposed query or files",
    "retry": "Retry this worker",
    "ask_stop": "Leave the worker and return to continue/stop",
    "replan": "Ask the planner to fill more of the catalog path",
    "add_hops": "Add hosts/hops (advanced typed payload)",
    "abandon_generation": "Give up on this generation path",
    "switch_to_both": "Allow the agent to fill remaining vulns (mode=both)",
    "submit": "Submit the form",
}

KIND_QUESTIONS: dict[str, str] = {
    "offer_idea": "What company / lab idea should we design?",
    "ask_stop": "Continue the interview, or stop?",
    "choose_next_move": "What should we do next?",
    "combined_form": "Configure vuln authorship, difficulty, and research",
    "extend_chain": "The plan is not ready. How do you want to proceed?",
    "ask_extra_paths": "Accept optional extra compromise paths?",
    "lab_up": "Bring the isolated lab up, skip, or take it down?",
    "hitl_tool": "Human approval required for a tool call",
    "worker_budget": "A worker hit a limit or timed out. What next?",
}


class InteractiveTUI:
    """Menu-driven TUI with DeepLabBuilder ASCII header."""

    def __init__(
        self,
        *,
        read: Callable[[], str] | None = None,
        write: Callable[[str], None] | None = None,
        use_rich: bool | None = None,
    ) -> None:
        self._read = read or (lambda: input())
        self._write = write or (lambda text: print(text, end="", flush=True))
        self._console = None
        self._use_rich = False
        if use_rich is not False:
            try:
                from rich.console import Console

                # When tests inject write(), keep output on that stream.
                if write is None:
                    self._console = Console(highlight=False, soft_wrap=True)
                    self._use_rich = True
            except ImportError:
                pass
        self._menu = AskMenu(read=self._read, write=self._write)
        self._header_shown = False

    def progress(self, message: str) -> None:
        if self._console is not None:
            self._console.print(f"⋯ {message}", style=THEME["progress"])
        else:
            self._write(f"[progress] {message}\n")

    def show(self, payload: dict[str, Any], *, hosts: list[dict] | None = None) -> Any:
        self._show_header()
        kind = str(payload.get("interrupt_kind") or "unknown")
        self._paint_context(payload, hosts=hosts)
        if kind == "combined_form":
            return self._combined_form()
        if kind == "offer_idea":
            return self._offer_idea(payload)
        if kind == "hitl_tool":
            return self._hitl(payload)
        if kind == "extend_chain":
            return self._extend_chain(payload)
        return self._menu_actions(payload)

    def _show_header(self) -> None:
        if self._header_shown:
            return
        self._header_shown = True
        if self._console is not None:
            from rich.panel import Panel
            from rich.text import Text

            body = Text(ASCII_HEADER + "\n", style=THEME["header"])
            body.append(TAGLINE, style=THEME["muted"])
            self._console.print(
                Panel(
                    body,
                    border_style=THEME["panel_border"],
                    padding=(0, 1),
                    title="DeepLabBuilder",
                )
            )
            return
        width = min(shutil.get_terminal_size((80, 24)).columns, 78)
        rule = "─" * width
        self._write(f"{rule}\n{header_block()}\n{rule}\n")

    def _paint_context(self, payload: dict[str, Any], *, hosts: list[dict] | None) -> None:
        kind = str(payload.get("interrupt_kind") or "unknown")
        lines: list[str] = []
        if payload.get("error"):
            lines.append(f"error: {_safe(payload.get('error'))}")
        if payload.get("detail"):
            lines.append(f"detail: {_safe(payload.get('detail'))}")
        if kind == "hitl_tool":
            lines.append(f"tool: {_safe(payload.get('tool'))}")
            args = payload.get("args") or {}
            if isinstance(args, dict):
                if payload.get("tool") == "write_session_files":
                    files = args.get("files") or {}
                    if isinstance(files, dict):
                        lines.append("files: " + ", ".join(_safe(n) for n in files))
                        for name, body in files.items():
                            text = _safe(body)
                            if len(text) > FILE_PREVIEW:
                                text = text[:FILE_PREVIEW] + "\n…[truncated]"
                            lines.append(f"----- {_safe(name)} -----")
                            lines.append(text)
                else:
                    for key, value in args.items():
                        if key == "files":
                            continue
                        lines.append(f"  {key}={_safe(value)}")
        if kind == "extend_chain":
            for err in payload.get("errors") or []:
                lines.append(f"  - {_safe(err)}")
        table = hosts or payload.get("hosts")
        if isinstance(table, list) and table:
            lines.append("hosts:")
            for host in table:
                if isinstance(host, dict):
                    lines.append(f"  {_safe(host.get('id'))} ({_safe(host.get('role'))})")
        block = "\n".join(lines) if lines else KIND_QUESTIONS.get(kind, kind)
        if self._console is not None:
            from rich.panel import Panel

            self._console.print(
                Panel(block, border_style=THEME["rule"], title=f"[{kind}]", padding=(0, 1))
            )
        else:
            self._write(f"[{kind}]\n{block}\n")

    def _options_from_allowed(self, allowed: list[Any]) -> list[MenuOption]:
        return [
            MenuOption(value=str(action), label=str(action), description=ACTION_HELP.get(str(action), ""))
            for action in allowed
        ]

    def _menu_actions(self, payload: dict[str, Any]) -> Any:
        kind = str(payload.get("interrupt_kind") or "unknown")
        allowed = list(payload.get("allowed") or payload.get("allowed_decisions") or [])
        question = KIND_QUESTIONS.get(kind, f"Choose an action for {kind}")
        if not allowed:
            return self._menu.ask_text(question) or "stop"
        choice = self._menu.ask(question, self._options_from_allowed(allowed))
        return "stop" if choice is None else choice

    def _offer_idea(self, payload: dict[str, Any]) -> Any:
        suggestions = list(payload.get("suggestions") or [])
        options = [
            MenuOption(value={"pick": i}, label=f"[{i}]", description=_safe(idea)[:90])
            for i, idea in enumerate(suggestions)
        ]
        options.append(MenuOption(value="__free__", label="Type my own idea", description="Free text"))
        choice = self._menu.ask(KIND_QUESTIONS["offer_idea"], options)
        if choice is None:
            return "stop"
        if choice == "__free__":
            return self._menu.ask_text("Describe the company / lab idea") or "stop"
        return choice

    def _combined_form(self) -> dict[str, Any]:
        mode = self._menu.ask(
            "Who authors lab issues?",
            [
                MenuOption("user", "user", "You list issue names only"),
                MenuOption("agent", "agent", "Planner invents from catalog roles"),
                MenuOption("both", "both", "Your list kept; planner fills the rest"),
            ],
        )
        if mode is None:
            return _parse_form("")
        fields: dict[str, Any] = {"action": "submit", "vuln_mode": str(mode)}
        if mode != "user":
            diff = self._menu.ask(
                "Difficulty (lab size when the planner invents)?",
                [
                    MenuOption("beginner", "beginner", "3 hosts / 2 hops"),
                    MenuOption("intermediate", "intermediate", "4 hosts / 3 hops"),
                    MenuOption("advanced", "advanced", "5 hosts / 4 hops"),
                    MenuOption("senior_expert", "senior_expert", "6 hosts / 5 hops"),
                ],
            )
            fields["difficulty"] = str(diff or "beginner")
        research = self._menu.ask(
            "Run public writeup research (Tavily) before planning?",
            [
                MenuOption(False, "No", "Skip research"),
                MenuOption(True, "Yes", "HITL-approve a query, then search"),
            ],
        )
        fields["research.opted_in"] = bool(research)
        if mode in ("user", "both"):
            vulns = self._menu.ask_text("User vuln names (pipe-separated, no PoCs). Empty = none")
            if vulns:
                fields["user_vulns"] = [v for v in vulns.split("|") if v.strip()]
        return fields

    def _hitl(self, payload: dict[str, Any]) -> Any:
        allowed = list(payload.get("allowed") or payload.get("allowed_decisions") or [])
        tool = str(payload.get("tool") or "tool")
        question = f"Approve {tool}?"
        if payload.get("error"):
            question = f"{tool} issue ({_safe(payload.get('error'))}). What next?"
        choice = self._menu.ask(question, self._options_from_allowed(allowed))
        if choice is None:
            if "reject" in allowed:
                return "reject"
            if "skip" in allowed:
                return "skip"
            return "stop"
        if choice != "edit":
            return choice
        if tool == "compose_cli":
            return "reject"
        if tool == "write_session_files":
            path = self._menu.ask_text("Relative path to edit (e.g. writeup.md)")
            body = self._menu.ask_text("New file body (use \\n for newlines)")
            rel = path.replace("\\", "/").lstrip("./")
            return {"action": "edit", "args": {"files": {rel: body.replace("\\n", "\n")}}}
        query = self._menu.ask_text("Edited search query")
        return {"action": "edit", "args": {"query": query}}

    def _extend_chain(self, payload: dict[str, Any]) -> Any:
        allowed = [str(a) for a in (payload.get("allowed") or [])]
        choice = self._menu.ask(KIND_QUESTIONS["extend_chain"], self._options_from_allowed(allowed))
        if choice is None:
            return "abandon_generation" if "abandon_generation" in allowed else "stop"
        if choice != "add_hops":
            return choice
        opts: list[MenuOption] = []
        if "replan" in allowed:
            opts.append(MenuOption("replan", "replan", "Let the planner expand the path"))
        if "switch_to_both" in allowed:
            opts.append(MenuOption("switch_to_both", "switch_to_both", "Allow agent fill"))
        opts.append(MenuOption("__typed__", "Type raw add_hops payload", "Advanced"))
        if "abandon_generation" in allowed:
            opts.append(MenuOption("abandon_generation", "abandon_generation", "Stop generating"))
        follow = self._menu.ask("add_hops needs a structured payload. Continue how?", opts)
        if follow is None:
            return "abandon_generation" if "abandon_generation" in allowed else "stop"
        if follow == "__typed__":
            return self._menu.ask_text("Raw resume value") or "abandon_generation"
        return follow
