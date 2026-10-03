"""Docker Compose CLI confined to a session compose directory."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from homelab_creator.spec.validators import compose_file, isolation_errors

ComposeRunner = Callable[[Sequence[str], Path], tuple[int, str]]
ALLOWED_ACTIONS = frozenset({"up", "down"})
LOG_CAP = 8000


def _clip(text: str) -> str:
    if len(text) <= LOG_CAP:
        return text
    return text[:LOG_CAP] + "\n…[truncated]"


def _default_runner(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            list(cmd),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, _clip(str(exc))
    out = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, _clip(out)


def compose_argv(action: str, compose_name: str) -> list[str]:
    """``docker compose`` argv for ``up --detach`` or ``down``. Other actions are rejected."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"unsupported compose action: {action}")
    cmd = ["docker", "compose", "-f", compose_name, action]
    if action == "up":
        cmd.append("--detach")
    return cmd


def run_compose(
    compose_dir: Path,
    action: str,
    *,
    session: Path | None = None,
    runner: ComposeRunner | None = None,
) -> tuple[int, str]:
    """Run compose up or down inside a real session ``compose/`` directory.

    Up is refused when the isolation linter fails. ``runner`` replaces the subprocess in tests.
    Returns ``(exit_code, clipped_output)``.
    """
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"unsupported compose action: {action}")
    directory = Path(compose_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("compose dir must be a real directory")
    if ".." in directory.parts:
        raise ValueError("compose dir must not contain ..")
    resolved = directory.resolve()
    if session is not None:
        expected = (Path(session) / "compose").resolve()
        if resolved != expected:
            raise ValueError("compose dir must be session compose/")
    found = compose_file(directory)
    if found is None or found.is_symlink():
        raise ValueError("compose file missing")
    if found.resolve().parent != resolved:
        raise ValueError("compose file must live in compose dir")
    if action == "up":
        text = found.read_text(encoding="utf-8")
        if isolation_errors(text):
            raise ValueError("isolation")
    cmd = compose_argv(action, found.name)
    execute = runner or _default_runner
    return execute(cmd, resolved)
