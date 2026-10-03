# Implementation: AI vulnerable homelab creator

Audience: experienced Python engineer, new to this repo. Language: Python 3.11+. Orchestration: **LangGraph 1.x outer graph** plus **Deep Agents workers** (both required). Also `langchain` 1.x LTS, `langchain-core` 1.x, `langsmith` ≥ 0.3, `langchain-openai` (OpenAI Chat Completions). Chat endpoint, API key, model, and `reasoning_effort` come from **`conf.yaml`** (`airouter:` block; copy `conf.example.yaml`). Default endpoint **airouter.ch** (`https://api.airouter.ch/v1`, model `Qwen3.8`, effort `medium`). Pin `deepagents` to a tested 0.7.x. Tests force heuristics (`HOMELAB_HEURISTIC=1`) and `tests/fixtures/conf.empty.yaml`. CLI uses Deep Agent workers when `airouter.api_key` is set. Run with `uv run homelab-creator --run`. Do not start on LangChain 0.3.

Do **not** paste large code samples. Follow project LangChain / LangGraph / Deep Agents skills. Lookup TUI or search SDKs with `/kk:dependency-handling` before imports.

## Repo layout (create as you go)

```
pyproject.toml          # package homelab_creator, script entry
src/homelab_creator/
  __init__.py
  __main__.py           # python -m homelab_creator → TUI
  tui/                  # interrupt renderer only
  graph/                # State, nodes, routing, compile
  workers/              # Deep Agent factories + invoke.py wrapper
  spec/                 # models + validators
  catalog/              # v1 Compose templates + allowed images
  tools/                # search, write_session_files, compose_cli
conf.example.yaml       # airouter.ch key / model / reasoning_effort
conf.yaml               # local copy, gitignored
tests/
```

Session data: **`./sessions/<thread_id>/`** (cwd) or user data dir — gitignored. Not under `src/`. `.env` gitignored. Checkpointer SQLite beside sessions (or in-memory in tests).

Verify: `python -c "import homelab_creator"` and `python -m homelab_creator --help` (or equivalent) after Task 0.

## Interrupt envelope

Every `interrupt()` value is a dict with at least:

- `interrupt_kind`: `offer_idea` \| `ask_stop` \| `choose_next_move` \| `combined_form` \| `extend_chain` \| `ask_extra_paths` \| `lab_up` \| `hitl_tool` \| `worker_budget`
- `allowed` (for menus): list of action ids
- HITL: `tool`, `args`, `allowed_decisions`. Search and file-write use approve/edit/reject. **Compose CLI is approve/reject only** (the up/down action is locked; containers are reached by static lab IPv4, not host ports).

The TUI switches on `interrupt_kind` only. Workers must not invent a second resume protocol. **Task 4** defines `hitl_tool` for search; **Task 6** for file write; **Task 8** for compose and **only renders** those payloads.

## State

`spec` (overwrite), `interrupt_kind`, `validation_errors` (overwrite), optional `planner_input_notes`, `agent_auto_replan_done`, `lab_up_detail`. Artifact fields (`artifacts`, `artifacts_stale`, `lab_up_status`) live **on `LabSpec`**, not as sibling graph keys. Partial updates only.

Verify: overwrite vs list-reducer test on a one-node graph.

## Persistence

Checkpointer required. Tests: `InMemorySaver`. v1 CLI default: SQLite (`sessions/checkpoints.sqlite` beside session dirs). Always `thread_id` (`[A-Za-z0-9_-]` only). Disk files (`spec.json`, topology, writeup, compose) are artifacts, not the checkpoint.

Verify: same thread resumes spec; other thread does not.

## Interview graph (human ring + worker batches)

Nodes: `offer_idea`, `ask_stop`, `choose_next_move`, `combined_form`, `research_worker`, `vuln_planner`, `extend_chain`, `ask_extra_paths`, `lab_builder`, `writeup_writer`, `lab_up`.

Routing laws (must match design.md “single routing law”):

- `choose_next_move` resume **dispatches immediately** to the table `Next` (no `ask_stop` in between).
- `combined_form` resume → research/plan batch immediately (no `ask_stop` in between). Set `form_completed=true` after a successful form resume.
- After `offer_idea`, after `ask_extra_paths` is answered, and after `lab_up` finishes (up/skip/fail) → `ask_stop`. Not after `extend_chain`.
- `ask_stop` + stop → END. Continue → **first-build shortcut** if plan-ready and no compose → `build`; else if plan-ready and `artifacts_stale` → `rebuild`; else `choose_next_move`.
- `hitl_tool` retry/skip stay in the same worker. `worker_budget` retry/skip stay in the same **research/plan** batch; `ask_stop` on that interrupt is the only budget path to `ask_stop`. Skip or HITL reject of `lab_builder` / `writeup` goes to `ask_stop` so writeup/`lab_up` never run without compose.
- Worker batches: `research → plan`; `lab_builder → writeup → lab_up`. No `ask_stop` inside a batch.
- Prefer `Command(goto=…)` **or** static edges from a node, not both.

`interrupt()` first in human nodes. Idempotent upserts only before interrupt.

**Worker budget:** `src/homelab_creator/workers/invoke.py` (or `graph/invoke_worker.py`) wraps **all** Deep Agent workers. Tests: stub that raises a budget error → `worker_budget`, graph does not END.

Verify: cannot END without `ask_stop` stop=true; after idea, continue → `choose_next_move` with `more_brainstorm` and `lock_idea_and_form` only; lock goes to `combined_form` without `ask_stop`; form resume starts research stub not `ask_stop`; extra_paths then continue with **plan-ready** and no compose auto-`build`s; not plan-ready does **not** auto-`build`; after redo with existing compose, continue auto-`rebuild`s (`artifacts_stale`).

## Combined form then research then plan

On `combined_form` resume: patch `vuln_mode`, `difficulty`, `research.opted_in`, `user_vulns`; `extra_paths_accepted` stays false until `ask_extra_paths` yes. Then research if opted in (HITL approve the query; Tavily if `search.api_key` / `TAVILY_API_KEY`; else airouter notes with empty citations; missing key → skip vs retry, never fake citations). Then planner. TUI streams `[progress]` between interrupts.

**Crash policy:** `invoke_worker` catches LLM/network failures (timeouts included). HITL offers `retry` / `skip` / `ask_stop` — same shape as `worker_budget`. `interrupt()` / `GraphBubbleUp` always propagates. After Tavily succeeds, notes are kept without a Deep Agent refine (avoids airouter timeout wiping a good search). Planner airouter failure keeps the catalog heuristic fill. Session `_advance` is a last-resort backstop so the CLI does not exit on an unexpected node exception.

Planner: keep user vulns. Invent/fill only for `agent` or `both`, using difficulty table + research notes, **catalog roles only**.

Validate **plan-ready**. Fail → `extend_chain` per design. **No** `ask_stop` in this loop. `abandon_generation` → `choose_next_move`, not plan-ready.

If plan-ready → `ask_extra_paths` (second path only on yes; set `extra_paths_accepted`; if compose already exists, set `artifacts_stale`). Then `ask_stop`, then first-build shortcut (plan-ready + no compose) or stale auto-`rebuild` or `choose_next_move`. After lab_builder + writeup, validate **artifact-ready** and clear `artifacts_stale`.

Verify: research notes reach planner only if opted in; user vulns persist in `both`; extra_paths false → one path; user-only invalid chain → `extend_chain` actions only, no silent agent fill.

## Catalog, topology, Compose, writeup, lab_up

`catalog/`: required `foothold`, `internal`, `crown_jewel`; extras `workstation`, `mail`, `jump`. Snippets must allow multiple instances of a role (unique service/host ids). Isolation baked in (bridge networks, **static IPv4, no host `ports:`**, no host mounts outside session, no privileged). Difficulty host-count minima only for `agent`/`both`.

`lab_builder` instantiates catalog ids from spec, writes `topology.md` + `compose/`. Run `docker compose -f … config` (no up) as a verifier in tests/CI when docker is available; schema-level isolation checks always.

`writeup_writer` always after successful lab_builder. Coupled rebuild: topology + compose + writeup together.

`lab_up`: HITL then `docker compose up -d` in the session compose dir. Resume skip is allowed (`lab_up_status=skipped`) but product success requires running or an explicit skip recorded. Down is HITL too.

Verify: single-host / non-catalog **role** fails **plan-ready**; non-catalog **image** fails compose HITL (not plan-ready); isolation linter fails **artifact-ready** on `network_mode: host`; writeup contains every host id; skip vs up sets `lab_up_status`.

## Tools and safety

- Search: dedicated package if used; Task 4 payload; TUI render-only.
- File writes: session directory only; upsert.
- Compose CLI: session compose dir only.
- Prompts: assessment language; no exploit PoCs in TUI. Coarse deny-list validator on chat/writeup strings.

## TUI

`show(payload) -> resume_value`. Banner pwn-the-company. Host table when topology exists. Stdio TUI + ScriptedTUI. Session loop streams LangGraph `updates`, then renders interrupts. Compose HITL is approve/reject only.

Verify: headless full script: idea → ask_stop → choose_next_move lock → form → workers → extra_path no → ask_stop → auto `build` → lab_up skip → ask_stop stop. Second continue shows `rebuild` not `lock_idea_and_form`.

## Testing approach

- Default CI: no live LLM; fake workers; golden specs including user-only deadlock and isolation.
- Graph tests: END conditions, choose_next_move allow-list, worker_budget.
- Optional `@pytest.mark.llm` and `@pytest.mark.docker`.

## Assumptions to invalidate in code

If worker HITL cannot share `interrupt_kind`, wrap tools in parent-graph tools instead of Deep Agent `interrupt_on`. If catalog cannot express a finding, fail validation and `extend_chain` rather than emitting a custom Dockerfile.
