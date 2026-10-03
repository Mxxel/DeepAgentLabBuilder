"""CLI entry: ``python -m homelab_creator``."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from homelab_creator.graph.compile import compile_graph
from homelab_creator.spec.validators import HOST_ID_RE
from homelab_creator.tui.interactive import InteractiveTUI
from homelab_creator.tui.session import run_session
from homelab_creator.tui.stdio import StdioTUI


def _default_session(thread_id: str) -> Path:
    """Return ``sessions/<thread_id>`` after rejecting ids that escape that directory."""
    if not HOST_ID_RE.fullmatch(thread_id):
        raise ValueError("thread-id must match [A-Za-z0-9][A-Za-z0-9_-]{0,62}")
    root = Path("sessions").resolve()
    session = (root / thread_id).resolve()
    if session != root and not str(session).startswith(str(root) + "/"):
        raise ValueError("thread-id escaped sessions/")
    return session


def main(argv: list[str] | None = None) -> int:
    """Start the interview when ``--run`` is set; otherwise print help and return 0.

    Artifacts land in ``./sessions/<thread-id>/`` unless ``--session-dir`` is set.
    ``--plain`` uses line input instead of numbered menus.
    """
    parser = argparse.ArgumentParser(
        prog="homelab-creator",
        description="Co-design an isolated, assessment-style vulnerable homelab.",
    )
    parser.add_argument("--run", action="store_true", help="start the interview TUI")
    parser.add_argument("--thread-id", default="", help="LangGraph thread id")
    parser.add_argument("--session-dir", default="", help="session directory (default ./sessions/<thread>)")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="plain line-input TUI (no menus / Rich chrome)",
    )
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    thread_id = args.thread_id.strip() or uuid.uuid4().hex
    if not HOST_ID_RE.fullmatch(thread_id):
        parser.error("thread-id must match [A-Za-z0-9][A-Za-z0-9_-]{0,62}")
    try:
        session = Path(args.session_dir).resolve() if args.session_dir.strip() else _default_session(thread_id)
    except ValueError as exc:
        parser.error(str(exc))
    session.mkdir(parents=True, exist_ok=True)
    persist = session.parent / "checkpoints.sqlite"
    graph = compile_graph(persist_path=persist)
    tui: StdioTUI | InteractiveTUI = StdioTUI() if args.plain else InteractiveTUI()
    run_session(tui, session_dir=session, thread_id=thread_id, graph=graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
