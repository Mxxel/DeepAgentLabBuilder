# Tasks: AI vulnerable homelab creator

> Design: [./design.md](./design.md)
> Implementation: [./implementation.md](./implementation.md)
> Status: done
> Created: 2026-10-03
> Not Doing: Qubes, Kubernetes/cloud, web UI, agent-ended sessions, exploit PoCs in TUI, class/multi-user, CTF scoring, extra paths unless user asks, freeform Dockerfiles, host network/privileged/host binds/host port publishes

## Task 0: Package skeleton
- **Status:** done
- **Depends on:** —
- **Size:** S
- **Can run in parallel with:** —
- **Docs:** [implementation.md#repo-layout-create-as-you-go](./implementation.md#repo-layout-create-as-you-go)

### Subtasks
- [x] 0.1 Add `pyproject.toml` for package `homelab_creator` (Python ≥ 3.10), `src/` layout, console/`python -m` entry
- [x] 0.2 Add `src/homelab_creator/__init__.py` and `__main__.py`; gitignore `.env`, `sessions/`, checkpointer db
- [x] 0.3 Verify: `python -c "import homelab_creator"` from an editable install

## Task 1: Spec models and validators
- **Status:** done
- **Depends on:** Task 0
- **Size:** M
- **Can run in parallel with:** Task 2
- **Slicing:** Contract-First
- **Docs:** [design.md#validation-plan-ready--artifact-ready--stopped](./design.md#validation-plan-ready--artifact-ready--stopped), [design.md#spec-conceptual](./design.md#spec-conceptual)

### Subtasks
- [x] 1.1 Create `src/homelab_creator/spec/models.py` — idea, idea_locked, form_completed, objective, vuln_mode, difficulty enum, research, hosts, networks, paths, extra_paths_accepted default false, catalog_ids, artifacts, artifacts_stale, lab_up_status
- [x] 1.2 Create `src/homelab_creator/spec/validators.py` — `plan_ready` (objective, hosts/roles, paths, extra-path flag, difficulty minima when agent invents) vs `artifact_ready` (compose match, isolation, writeup)
- [x] 1.3 Golden tests under `tests/spec/` — plan-ready catalog company without compose files; fail plan-ready single-service/no-path; fail extra path without flag (default false); fail non-catalog role; fail artifact-ready `network_mode: host`; fail user-only invalid chain marked plan-ready; agent beginner missing 3 hosts fails plan-ready; `user_defined` 3-role path can be plan-ready; plan-ready ∧ no compose does not require writeup yet

## Task 2: Interview ring (idea, ask_stop, choose_next_move)
- **Status:** done
- **Depends on:** Task 0
- **Size:** M
- **Can run in parallel with:** Task 1
- **Slicing:** Risk-First
- **Docs:** [design.md#interview-sequence-single-routing-law](./design.md#interview-sequence-single-routing-law), [design.md#choose_next_move-contract](./design.md#choose_next_move-contract), [implementation.md#interview-graph-human-ring--worker-batches](./implementation.md#interview-graph-human-ring--worker-batches)

### Subtasks
- [x] 2.1 Create `src/homelab_creator/graph/state.py` and `compile.py` — StateGraph, checkpointer, `thread_id`, interrupt envelope; add `src/homelab_creator/workers/invoke.py` passthrough wrapper (Task 4 adds budget handling)
- [x] 2.2 Implement `offer_idea`, `ask_stop`, `choose_next_move` — interrupt first; END only on stop=true; continue never implicit `combined_form`
- [x] 2.3 Headless tests — stop ends; continue after idea exposes `more_brainstorm` and `lock_idea_and_form` (not `redo_form`); lock dispatches to `combined_form` without `ask_stop`; unknown choose action re-interrupts; stub worker completion does not END; first-build shortcut requires **plan-ready**

## Task 3: Combined form + research-then-plan wiring
- **Status:** done
- **Depends on:** Task 1, Task 2
- **Size:** M
- **Can run in parallel with:** —
- **Docs:** [design.md#interview-sequence-single-routing-law](./design.md#interview-sequence-single-routing-law), [implementation.md#combined-form-then-research-then-plan](./implementation.md#combined-form-then-research-then-plan)

### Subtasks
- [x] 3.1 `combined_form` payload + spec patch; set `form_completed`; `lock_idea_and_form` / `redo_form` edges; form resume starts research/plan batch not `ask_stop`
- [x] 3.2 Conditional skip research; always planner after research-or-skip; no `ask_stop` inside the batch
- [x] 3.3 Stub tests — notes in planner input only if opted in; user vulns retained in `both`

## Task 4: Research worker
- **Status:** done
- **Depends on:** Task 3
- **Size:** M
- **Can run in parallel with:** Task 5
- **Docs:** [implementation.md#interrupt-envelope](./implementation.md#interrupt-envelope), [implementation.md#tools-and-safety](./implementation.md#tools-and-safety)

### Subtasks
- [x] 4.1 Extend `src/homelab_creator/workers/invoke.py` — all workers go through it; budget → `worker_budget` (retry/skip/ask_stop); `hitl_tool` resumes same batch (no `ask_stop`)
- [x] 4.2 `src/homelab_creator/workers/research.py` — Deep Agent via wrapper; notes + citations; no exploit recipes
- [x] 4.3 Define `interrupt_kind: hitl_tool` payload for search (approve/edit/reject); missing key → skip vs retry, never fake citations
- [x] 4.4 Tests with fake search — schema filled; opted-out does not call tool; stub budget error does not END

## Task 5: Vuln planner, extra-path, extend_chain
- **Status:** done
- **Depends on:** Task 3
- **Size:** M
- **Can run in parallel with:** Task 4
- **Docs:** [design.md#difficulty-enum](./design.md#difficulty-enum), [design.md#extend_chain](./design.md#extend_chain)

### Subtasks
- [x] 5.1 `src/homelab_creator/workers/planner.py` via invoke wrapper — required roles + extras/multi-instance; difficulty host/hop minima only for `agent`/`both`
- [x] 5.2 `ask_extra_paths`; on yes second path + `extra_paths_accepted=true`
- [x] 5.3 `extend_chain` — user: `switch_to_both` \| `add_hops` \| `abandon_generation`; agent/both: one auto-replan then `replan` \| `add_hops` \| `abandon_generation`; no `ask_stop` in the loop
- [x] 5.4 Tests — beginner vs senior_expert minima; extra-path no/yes; user-only invalid chain not plan-ready and no invented vulns; agent invalid → one auto-replan then interrupt; not plan-ready does not first-build; `build` absent unless plan-ready; redo with existing compose sets `artifacts_stale` and continue auto-rebuilds

## Task 6: Catalog + topology + Compose builder
- **Status:** done
- **Depends on:** Task 1, Task 5
- **Size:** M
- **Can run in parallel with:** —
- **Docs:** [design.md#runtime-v1](./design.md#runtime-v1), [implementation.md#catalog-topology-compose-writeup-lab_up](./implementation.md#catalog-topology-compose-writeup-lab_up)

### Subtasks
- [x] 6.1 `src/homelab_creator/catalog/` — required foothold/internal/crown_jewel; extras workstation/mail/jump; multi-instance ids; isolation defaults
- [x] 6.2 `src/homelab_creator/workers/lab_builder.py` via invoke wrapper — instantiate catalog into session `topology.md` + `compose/`; file-write HITL payload (`hitl_tool`)
- [x] 6.3 Tests — compose_matches_topology; single-host fails; isolation linter; compose up **not** in this task

## Task 7: Writeup always + coupled rebuild
- **Status:** done
- **Depends on:** Task 6
- **Size:** S
- **Can run in parallel with:** —
- **Docs:** [design.md#choose_next_move-contract](./design.md#choose_next_move-contract)

### Subtasks
- [x] 7.1 `src/homelab_creator/workers/writeup.py` via invoke wrapper — after successful lab build; inventory, hops, citations iff research
- [x] 7.2 `build` if plan-ready and no compose; auto-`rebuild` if plan-ready and `artifacts_stale`; `rebuild` if compose exists; first-build shortcut after extra_paths continue; clear `artifacts_stale` after successful artifact-ready
- [x] 7.3 Tests — missing writeup is not artifact-ready; citations empty iff research skipped; plan-ready without compose is enough to `build`; stale compose after redo auto-rebuilds on continue

## Task 8: TUI, compose HITL, lab_up
- **Status:** done
- **Depends on:** Task 2, Task 7
- **Size:** M
- **Can run in parallel with:** —
- **Docs:** [implementation.md#tui](./implementation.md#tui), [design.md#success](./design.md#success)

### Subtasks
- [x] 8.1 TUI adapter after `/kk:dependency-handling` — render **all** `interrupt_kind`s including Task 4/6 `hitl_tool` (do not redefine payloads)
- [x] 8.2 `lab_up` node: HITL compose up/down in session dir; skip records `lab_up_status=skipped`
- [x] 8.3 Headless scripted session: lock idea → form stubs → extra_path no → ask_stop continue auto-`build` → lab_up skip → ask_stop stop; later continue offers `rebuild` not `lock_idea_and_form`; redo then continue auto-`rebuild`s; optional `@pytest.mark.docker` smoke

## Task 9: Final verification
- **Status:** done
- **Depends on:** Task 0, Task 1, Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8
- **Size:** S
- **Can run in parallel with:** —

### Subtasks
- [x] 9.1 Run `/kk:test` — full suite including graph END, choose_next_move, user-only extend_chain, isolation goldens
- [x] 9.2 Run `/kk:document` — README/session usage if user-facing docs exist
- [x] 9.3 Run `/kk:review-code` with Python
- [x] 9.4 Run `/kk:review-spec` against `docs/wip/vulnerable-homelab-creator/`

## Dependency Graph

```
Task 0 ─┬─→ Task 1 ─┐
        │           ├─→ Task 3 ─┬─→ Task 4 ─┐
        └─→ Task 2 ─┘           └─→ Task 5 ─┴─→ Task 6 ─→ Task 7 ─→ Task 8 ─→ Task 9
```
