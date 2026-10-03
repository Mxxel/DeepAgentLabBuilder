# Design: AI vulnerable homelab creator

> Status: approved for implementation (post design-review)  
> Users: homelab hobbyist (v1)  
> Stack: custom TUI + LangGraph outer loop + Deep Agent workers + Docker Compose  
> Created: 2026-10-03

## Problem

A homelab hobbyist wants to **co-design** an intentionally vulnerable practice environment through conversation, then leave the TUI with a **running lab**, a **matching writeup**, and a **detailed topology** — in one sitting. Today they assemble boxes by hand or play CTFs that do not feel like assessments.

## How might we

How might we co-design a realistic assessment-style homelab through a **multi-step interview that never ends itself**, where after the user’s idea is **locked**, **one form** covers vulnerability authorship (user / agent / both), difficulty (four levels), and optional research of real pentests and public bug bounty writeups — research runs **before** the agent invents issues — without collapsing into a toy CTF?

## Success

One sitting in the TUI: interview → artifacts → **HITL `docker compose up`** so the lab is **running**, plus **writeup** and **topology**, without switching apps. The session does not end unless the user confirms stop. Files on disk without a successful (or explicitly skipped) lab-up step do **not** count as success.

## Product rules (invariants)

1. **Human-step ring (with carve-outs).** `ask_stop` runs after **menu** interrupts (`offer_idea`, `ask_extra_paths`, `lab_up` finished). It does **not** run after `choose_next_move` or `combined_form` (those dispatch immediately). It does **not** run in the `extend_chain` loop. It does **not** run for `hitl_tool` or `worker_budget` retry/skip. END only when the user confirms stop on `ask_stop`. Workers never route to END.
2. **Brainstorm until lock.** Idea rounds may repeat. Continue after an idea does **not** jump to the vuln form. The user must choose **more brainstorming** or **lock idea and open the vuln/research form**.
3. **Combined vuln + research form.** One resume payload: vuln source (user / agent / both), difficulty when the agent invents anything, research yes/no.
4. **Research before invention.** If research is yes, public pentest/bug-bounty notes are gathered first; then the planner invents or fills vulns. User-named vulns are always kept.
5. **Always pwn the company.** `objective` is full network / company control. A single-flag box is invalid.
6. **Always topology.** Networks, every host’s service stack, every host’s vulnerabilities. Compose service names must match host ids.
7. **Always writeup.** Same spec as the lab; citations when research ran.
8. **Extra paths optional.** After a valid primary chain, ask whether to add another way to succeed. Not required. Yes adds a second chain without deleting the first.
9. **No exploit factory.** TUI shows assessment-style issues and environment facts, not exploit PoCs or attack playbooks.
10. **HITL** on web fetch, writing lab files, and `docker compose` up/down.
11. **Catalog labs only (v1).** Roles: **required** `foothold`, `internal`, `crown_jewel`; **optional extras** `workstation`, `mail`, `jump`. The planner may instantiate a role **more than once** with distinct host ids (e.g. `workstation-1`, `workstation-2`). No freeform Dockerfiles or images outside the catalog.
12. **Local isolation.** Compose uses project-local bridge networks (not `host` network), assigns each container a **static IPv4 on those networks**, and does **not** publish host ports (`ports:` / `127.0.0.1` / `0.0.0.0`). Reach every service by its lab network IP. Do not bind host paths outside the session dir, and do not set `privileged: true`.

## Architecture

**LangGraph owns the session.** Compiled `StateGraph` + checkpointer + `thread_id`. Human nodes call `interrupt()` first. Every interrupt payload includes `interrupt_kind` so the TUI uses one envelope for parent questions and worker HITL (`hitl_tool`).

**Deep Agents are workers**, invoked as graph nodes. They return spec/artifact updates only; the parent routes. HITL tools must surface as `interrupt_kind: hitl_tool` (same TUI resume path). Default subgraph checkpointer (interrupts OK). Side-effecting file writes happen in **post-interrupt** parent nodes or upsert-only.

**TUI** is the only UI. Adapter: `show(payload) -> resume_value`. The session driver streams graph `updates` then reads interrupts from `get_state`. Banner: objective = pwn the company.

**Session directory** lives **outside the package** (cwd `./sessions/<thread_id>/` or the user data dir). Never `src/homelab_creator/sessions/`. Contents: `spec.json`, `topology.md`, `writeup.md`, `compose/`.

```
TUI  ←interrupt/resume→  Outer LangGraph ring
                              │
                              ├─ research worker (skip if no)
                              ├─ vuln planner
                              ├─ extra-path interrupt
                              ├─ lab builder (catalog → Compose + topology)
                              ├─ writeup writer (always)
                              └─ lab_up (HITL compose up)
```

## Interview sequence (single routing law)

There is no `pending_action`. `ask_stop` continue goes to: **first-build** if plan-ready and no compose; else **stale `rebuild`** if plan-ready and `artifacts_stale`; else `choose_next_move`.

Happy path:

1. `offer_idea` → `ask_stop` → continue → `choose_next_move`
2. User picks `lock_idea_and_form` → **immediate** `combined_form` (no `ask_stop` in between)
3. `combined_form` resume → **immediate** research (if opted in) → planner → validate (`hitl_tool` / `worker_budget` retry stay in this batch)
4. Invalid → `extend_chain` (not END). After a resolving resume, re-enter planner (user-only rules below). If still invalid, `extend_chain` again.
5. Valid → `ask_extra_paths` → `ask_stop`
6. **First-build shortcut:** continue while **plan-ready** (see Validation) and `compose/` does **not** exist → **immediate** `build` (lab_builder + writeup + `lab_up`) → `ask_stop`. Hosts/paths alone are not enough.
7. Any later continue → if **plan-ready** and `artifacts_stale` → **immediate `rebuild`**; else `choose_next_move` (`build` if plan-ready and no compose, `rebuild` if compose exists, etc.)

## choose_next_move contract

Resume **dispatches immediately** (table `Next`). Stop is only `ask_stop`.

| Action | When allowed | Next |
|--------|----------------|------|
| `more_brainstorm` | always | `offer_idea`. Sets `idea_locked=false`. Does **not** clear `form_completed`. |
| `lock_idea_and_form` | idea non-empty **and** `form_completed` is false | `combined_form`; sets `idea_locked=true` |
| `redo_form` | `form_completed` is true | `combined_form` then research/plan batch; sets `idea_locked=true` |
| `ask_extra_paths` | **plan-ready** (≥1 valid path) | extra-path interrupt |
| `build` | **plan-ready** and session `compose/` missing | lab_builder + writeup + `lab_up` |
| `rebuild` | session `compose/` exists | lab_builder + writeup + `lab_up`; then artifact validators; clear `artifacts_stale` |
| `lab_up` | `compose/` exists | HITL compose up |
| *(stop)* | — | not on this menu |

Unknown resume values re-interrupt. Payload `allowed` is exactly the currently allowed rows. After lock, further brainstorm uses `more_brainstorm` then `redo_form` (not `lock_idea_and_form`) once the form has been completed.

**Stale artifacts:** set `artifacts_stale=true` whenever a **plan-ready** spec changes while `compose/` exists (`redo_form` that yields a new plan, extra-path yes that adds a path, `extend_chain` that changes hosts/paths). Do not delete `compose/` (HITL down is safer). `ask_stop` continue then **auto-`rebuild`** (same as first-build shortcut, but compose already there). `choose_next_move` must include `rebuild` while stale; `lab_up` alone is not enough to clear stale.

## extend_chain

If validators fail (no path to company control), **never END**.

**`user` mode** — planner must not invent issues. Resume is exactly one of:

| Resume | Next |
|--------|------|
| `switch_to_both` | set mode `both`, planner fills gaps |
| `add_hops` | user supplies more vulns/hops, then planner (still no invention beyond what they added) |
| `abandon_generation` | `choose_next_move`, spec not ready |

**`agent` or `both`** — exactly **one** automatic replan that may add hops. If still invalid, interrupt `extend_chain` with resume exactly one of:

| Resume | Next |
|--------|------|
| `replan` | one more planner pass (not a silent loop; each extra pass needs this resume) |
| `add_hops` | user supplies hops, then planner |
| `abandon_generation` | `choose_next_move`, spec not ready |

No `ask_stop` in this loop. `abandon_generation` goes to `choose_next_move` with spec **not** plan-ready (no END, no auto-`build`).

## Difficulty (enum)

Exactly four values. Planner tests must use these bars (minimums):

| Level | Hosts | Hops (edges on the primary path = `len(hops)-1`) | Clue strength |
|-------|-------|--------------------------|---------------|
| `beginner` | 3 | 2 | obvious creds / misconfig |
| `intermediate` | 4 | 3 | some hunting |
| `advanced` | 5 | 4 | weaker clues |
| `senior_expert` | 6 | 5 | segmented, still solvable |

`user_defined` is stored when mode is user-only (no invention). Host/hop **minima apply only** when the agent invents (`agent` or `both`). User-only still needs a path to company control and catalog roles only; it is not failed for missing expert host counts.

Required company shape when the agent invents: at least one host of each required role; extra hosts use extras and/or extra instances. Objective is always full compromise.

## Spec (conceptual)

- `idea`, `idea_locked` (bool), `form_completed` (bool), `objective` (always full compromise)
- `vuln_mode`: user | agent | both
- `difficulty`: beginner \| intermediate \| advanced \| senior_expert \| user_defined
- `research`: { opted_in, notes[], citations[] }
- `hosts[]`: id, role (catalog role), networks, stack, vulns[], accounts
- `networks[]`, `paths[]` (≥1 when ready)
- `extra_paths_accepted`: bool, **default false** (exactly one path until the user accepts extras)
- `catalog_ids[]` instantiated host ids (not role names)
- `artifacts`, `artifacts_stale`: bool
- `lab_up_status`: not_run \| running \| skipped \| failed

## Validation (plan-ready ≠ artifact-ready ≠ stopped)

**Plan-ready** (may offer `build` / first-build shortcut; Compose may be absent):

- Objective is full network control
- Hosts have roles ⊆ catalog (required + extras; multi-instance ids allowed)
- ≥1 compromise path; extra paths only if `extra_paths_accepted` (default **false** → exactly one path on first plan-ready, **before** `ask_extra_paths`)
- Difficulty host/hop minima **only** if `vuln_mode` is `agent` or `both`
- Per-host stack + vulns present on the spec (topology fields in spec, even before `topology.md`)

**Artifact-ready** (after `lab_builder` + writeup; required before treating files as complete):

- `topology.md` + compose names match host ids
- Isolation constraints hold on generated compose
- Writeup maps findings ↔ hosts ↔ hops; citations iff research ran
- TUI output has no exploit-PoC dumps

**Product success:** artifact-ready **and** `lab_up_status` is `running` or `skipped`.

Stopped is independent: user confirmed stop.

## Runtime (v1)

**Template catalog** in-repo (Compose fragments / allowed images per role). Planner assigns findings to catalog roles. Lab builder instantiates the catalog, fills seed data, writes topology.

Isolation as in rule 12. Qubes later, same spec.

**Worker budget:** every worker (research, plan, lab build, writeup) is invoked through one wrapper. On recursion/tool budget: `worker_budget` with retry / skip this worker / go to `ask_stop`. Retry/skip resume the batch; they are not `ask_stop`. That interrupt is not END.

## Assumptions

- Outer-graph `interrupt()` plus one `interrupt_kind` envelope can drive the TUI, including worker HITL.
- Workers can return data only; parent owns routing and END.
- Required catalog roles plus extras/multi-instance are enough to hit the senior_expert host-count bar.
- Coupled rebuilds keep compose, topology, and writeup aligned.
- Public writeups can inform vuln **classes** without exploit recipes in chat.
- “Both” = user list kept + agent fills remainder from difficulty + research.

## Not doing (v1)

- Qubes (planned later)
- Kubernetes / cloud
- Web UI
- Agent-ended sessions
- Exploit PoCs / attack playbooks in the TUI
- Trainer/class multi-user, scoring boards, CTF-first design
- Inventing extra compromise paths unless the user says yes
- Freeform Dockerfile / arbitrary image generation
- `host` network, host filesystem binds outside the session dir, `privileged: true`

## Rejected alternatives

- **Deep Agent only:** “never end yourself” in a system prompt is too weak.
- **LangGraph only:** would rebuild planning, files, and subagents already provided by Deep Agents.
- **Jump to combined_form on first continue:** contradicts multi-step idea brainstorming (design review).

## Open questions for implementers (non-blocking)

- Concrete TUI library: choose via `/kk:dependency-handling`; contract is interrupt payload in / resume out.
- Concrete search provider: pluggable; dedicated package if used; Task 4 owns HITL payload shape, TUI only renders.
- Default chat model: OpenAI-compatible Chat Completions via **airouter.ch**, configured in `conf.yaml` (`api_key`, `model`, `reasoning_effort`).
