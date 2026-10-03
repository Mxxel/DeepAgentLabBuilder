# Code map

Package `homelab_creator` (console script `homelab-creator`). Product rules and the interview sequence live in the design pack: [docs/wip/vulnerable-homelab-creator/design.md](wip/vulnerable-homelab-creator/design.md). This page says where that behavior is implemented.

## Layout

| Path | Role |
| --- | --- |
| `__main__.py` | CLI. `--run` starts a session; `--plain` selects line input. |
| `config.py` | Loads `airouter` settings from `conf.yaml`, `HOMELAB_CONF`, then environment variables. |
| `spec/models.py` | `LabSpec` and the catalog role, difficulty, and lab-up enums. |
| `spec/validators.py` | `plan_ready` vs `artifact_ready`, plus the Compose isolation linter. |
| `spec/safety.py` | Coarse deny-list shared by research notes and the writeup. |
| `graph/compile.py` | Interview ring: `offer_idea`, `ask_stop`, `after_stop`, `choose_next_move`, and `compile_graph`. |
| `graph/nodes.py` | Form, workers, extend-chain, extra paths, lab build, writeup, and lab up. |
| `graph/state.py` | `GraphState`. The spec is overwritten as a whole. |
| `graph/envelope.py` | Interrupt payloads. Every payload has `interrupt_kind`. |
| `graph/checkpoint.py` | SQLite saver used by the CLI. Tests pass their own checkpointer. |
| `graph/session.py` | Session directory confinement. Writes do not follow symlinks. |
| `workers/invoke.py` | Wraps every worker. Budget and network failures become retry, skip, or ask-stop. |
| `workers/research.py` | HITL query, then Tavily notes and citation URLs. |
| `workers/planner.py` | Catalog fill. User mode does not invent issues. |
| `workers/agents.py` | Deep Agent factories. They return data; the parent graph routes. |
| `workers/lab_builder.py` | Catalog render, then file-write approval, then `compose/` and `topology.md`. |
| `workers/writeup.py` | Assessment writeup. Citations appear only when research ran. |
| `workers/llm.py` | Chat model. `HOMELAB_HEURISTIC=1` disables live calls. |
| `catalog/render.py` | Compose YAML and topology markdown. Images come from the role table. |
| `tools/search.py` | Tavily client. Drops deny-listed snippets. |
| `tools/compose_cli.py` | `docker compose up --detach` and `down`, only inside the session `compose/` directory. |
| `tui/session.py` | `show(payload) -> resume` loop over graph interrupts. |
| `tui/interactive.py` | Default numbered menus. |
| `tui/stdio.py` | `--plain` line input. |
| `tui/headless.py` | `ScriptedTUI` for tests. |
| `tui/render.py` | Text for one interrupt. Does not define a second resume protocol. |
| `tui/progress.py` | `[progress]` lines between interrupts. |

## How a session moves

`compile_graph` starts at `offer_idea`. Human nodes call `interrupt()` before they change the spec. The TUI switches only on `interrupt_kind`.

Continue after `ask_stop` goes to `after_stop`:

- Plan-ready and no compose file: `lab_builder` (first build).
- Plan-ready and `artifacts_stale`: `lab_builder` (rebuild).
- Otherwise: `choose_next_move`, which dispatches the chosen action immediately.

`combined_form` goes straight to `research_worker` or `vuln_planner`. An invalid plan goes to `extend_chain`, which does not end the session. A valid plan goes to `ask_extra_paths`, then `ask_stop`.

The build batch is `lab_builder` → `writeup_writer` → `lab_up`. Skipping the lab builder or the writeup returns to `ask_stop` so lab-up does not run without compose.

Stop on `ask_stop` is the only edge to END.

## What “ready” means

`is_plan_ready` allows a build. It requires full network compromise, catalog roles, a compromise path, and (when the planner invents issues) the difficulty host and hop minima. Compose files are not required yet.

`is_artifact_ready` checks the files after the build: topology and writeup name every host, compose service names match host ids, isolation holds, and the writeup has citations only when research ran.

Product success is artifact-ready and `lab_up_status` of `running` or `skipped`.

## Session files

Default directory: `./sessions/<thread-id>/`. Checkpoint database: `sessions/checkpoints.sqlite`. Both are gitignored.

| File | Writer |
| --- | --- |
| `spec.json` | `persist_spec` |
| `compose/docker-compose.yml` | `run_lab_builder` |
| `topology.md` | `run_lab_builder` |
| `writeup.md` | `run_writeup` |

## Configuration

Copy `conf.example.yaml` to `conf.yaml` (gitignored). `HOMELAB_CONF` overrides the path. Tests set `HOMELAB_HEURISTIC=1` and use `tests/fixtures/conf.empty.yaml`.

## Related

- [changelog.md](../changelog.md)
- [ADR 0001](adr/0001-langgraph-session-deep-agent-workers.md)
- [Design](wip/vulnerable-homelab-creator/design.md)
- [Implementation notes](wip/vulnerable-homelab-creator/implementation.md)
