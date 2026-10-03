# ADR 0001: LangGraph owns the session; Deep Agents are workers

- Status: accepted
- Date: 2026-10-03

## Context

The interview must not end unless the operator confirms stop. Idea rounds, the vuln form, research, planning, file writes, and `docker compose` up/down each pause for a human. A single agent prompt cannot enforce that routing.

Deep Agents already provide planning, file tools, and subagents. Rebuilding those inside graph nodes would duplicate that runtime.

## Decision

A compiled LangGraph `StateGraph` owns the session: interrupts, `thread_id`, the checkpointer, and every edge including END. Deep Agents run only as workers (`workers/agents.py`) and return spec or note updates. The parent graph routes. Human approval uses one interrupt envelope (`interrupt_kind`), including worker tool approval (`hitl_tool`).

Side-effecting writes happen in parent nodes after that approval (`graph/session.py`, `workers/lab_builder.py`, `workers/writeup.py`).

## Consequences

- END is reachable only from `ask_stop` when the resume is stop (`graph/compile.py`).
- Worker failures stay inside `workers/invoke.py` as retry, skip, or ask-stop. They do not end the graph by themselves.
- Tests can replace the checkpointer, the search function, and the compose runner without a live model or Docker.
- Adding a new pause means a new `interrupt_kind` and a TUI branch in `tui/render.py` and `tui/interactive.py`. Workers must not invent a second resume protocol.

## Alternatives

- Deep Agent only. “Never end yourself” in a system prompt does not stop the agent from finishing the turn. Rejected.
- LangGraph only. The outer loop would reimplement planning, file tools, and subagents that Deep Agents already provide. Rejected.

The same choice is recorded under Rejected alternatives in [design.md](../wip/vulnerable-homelab-creator/design.md).
