"""SQLite checkpointer for v1 CLI sessions. Tests keep InMemorySaver."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

# Existing sessions/checkpoints.sqlite may still contain these enums.
CHECKPOINT_MSGPACK_ALLOW = (
    ("homelab_creator.spec.models", "Difficulty"),
    ("homelab_creator.spec.models", "LabUpStatus"),
    ("homelab_creator.spec.models", "VulnMode"),
)


def checkpoint_serde() -> JsonPlusSerializer:
    """Serializer that can still load older checkpoints that stored spec enums."""
    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_MSGPACK_ALLOW)


def sqlite_saver(path: Path) -> SqliteSaver:
    """Open a SQLite checkpointer at ``path``, creating the parent directory and schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(conn, serde=checkpoint_serde())
    saver.setup()
    return saver
