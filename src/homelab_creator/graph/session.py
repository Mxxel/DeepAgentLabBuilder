"""Session directory confinement for stub writers."""

from __future__ import annotations

import errno
import os
from pathlib import Path

from homelab_creator.graph.state import GraphState


_SYMLINK_ERRNOS = {errno.ELOOP}
if hasattr(errno, "EMLINK"):
    _SYMLINK_ERRNOS.add(errno.EMLINK)


def resolve_session_dir(state: GraphState) -> Path:
    """Resolve ``session_dir`` from state. Rejects ``..`` segments and symlinks."""
    raw = state.get("session_dir")
    if not raw or not str(raw).strip():
        raise ValueError("session_dir required")
    path = Path(str(raw))
    if ".." in path.parts:
        raise ValueError("session_dir must not contain ..")
    if path.is_absolute():
        current = Path(path.anchor)
        parts = path.parts[1:]
    else:
        current = Path.cwd()
        parts = path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("session_dir must not be a symlink")
    return path.resolve()


def mkdir_session_child(session: Path, name: str) -> Path:
    """Create a real directory under the session. A symlink at that path is refused."""
    child = session / name
    if child.is_symlink():
        raise ValueError(f"refusing symlink: {child}")
    child.mkdir(parents=True, exist_ok=True)
    if child.is_symlink() or not child.is_dir():
        raise ValueError(f"refusing symlink: {child}")
    return child


def _raise_open_error(path: Path, exc: OSError) -> None:
    if exc.errno in _SYMLINK_ERRNOS:
        raise ValueError(f"refusing symlink: {path}") from exc
    raise exc


def persist_spec(session: Path, spec: object) -> None:
    """Write ``spec.json`` inside the session directory."""
    dump = spec.model_dump_json(indent=2) if hasattr(spec, "model_dump_json") else str(spec)
    write_session_file(session / "spec.json", dump)


def write_session_file(path: Path, text: str) -> None:
    """Overwrite one session file without following a symlink on the path or its parent."""
    parent = path.parent
    if path.is_symlink() or parent.is_symlink():
        raise ValueError(f"refusing symlink: {path}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    dir_flags = os.O_RDONLY | directory | nofollow
    try:
        dir_fd = os.open(parent, dir_flags)
    except OSError as exc:
        _raise_open_error(parent, exc)
    try:
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | nofollow
        try:
            fd = os.open(path.name, file_flags, 0o644, dir_fd=dir_fd)
        except OSError as exc:
            _raise_open_error(path, exc)
        try:
            os.write(fd, text.encode("utf-8"))
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
