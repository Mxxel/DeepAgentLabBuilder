# DeepLabBuilder (homelab-creator)

Build your homelabs with KI. More time for the fun part :)

This is just a pre-alpha version i build on an evening while thinking about how to simplify the process of creating vulnerable Homelabs, because from my experience HackTheBox and TryHackMe most machines are not reensembling what is awaiting you if pwning a real world infrastructure.
The best part: Totally free if you run your own local AI!

The goal of this project is to have an LLM based homelab creator, for now the lab network is created via docker.

To avoid CTF like labs i implemented a research function with tavily which fetches bug bounty writeups and creates the vulnerabilitys from them, you also can add own input.

You can view this as a base skeleton everyone is invited to work on so you can use more time to train your security skills instead of setting up configs for labs.

Everyone is invited to contribute and, in my vision this should be developed by those wo use it, every idea / feature / fix / extension is welcome, as long as no backdoors are included :D.

## Description

Interview TUI that co-designs isolated, assessment-style vulnerable homelabs (Docker Compose). The session never ends itself: you confirm stop. Objective is always **pwn the company** (full network control), not a single-flag box. Design pack: `docs/wip/vulnerable-homelab-creator/`. Code map: `docs/code.md`. Changelog: `changelog.md`.

The TUI shows assessment facts (hosts, stacks, issues, topology, writeup). It does **not** print exploit PoCs or attack playbooks.

## Install and run

```bash
# from the repo root, with conf.yaml filled in
uv run homelab-creator --run
```

`uv run` creates `.venv`, installs this package (editable) plus dependencies from `pyproject.toml`, then runs the console script. Equivalent:

```bash
uv run python -m homelab_creator --run
```

Tests:

```bash
uv run --extra dev pytest
```

If `uv` is not on `PATH`, use `~/.local/bin/uv` or install from https://docs.astral.sh/uv/.

Optional flags: `--thread-id`, `--session-dir`. Help: `uv run homelab-creator --help` (add `--run` to start the interview).

## Model (airouter.ch)

Workers use the **OpenAI Chat Completions** API through [AI Router Switzerland](https://airouter.ch/docs.html). **Key, model, and reasoning effort** are read from `conf.yaml` at the repo root (gitignored). Copy `conf.example.yaml`:

```yaml
airouter:
  base_url: https://api.airouter.ch/v1
  api_key: "sk-…"          # dashboard key
  model: Qwen3.8           # or DeepSeek-V4-Flash
  reasoning_effort: medium # Qwen: none|low|medium|xhigh  DeepSeek: high|xhigh
```

Override the file path with `HOMELAB_CONF`. Empty `api_key` may fall back to `AIROUTER_API_KEY`. Tests set `HOMELAB_HEURISTIC=1` and never call the network.

Research (`research.opted_in=true`) HITL-approves a public-writeup **query**, then **Tavily** search if `search.api_key` (or `TAVILY_API_KEY`) is set. airouter refines finding classes. Citations come from Tavily URLs only (never invented). Tests set `HOMELAB_HEURISTIC=1` and skip live Tavily. Between interrupts the TUI prints `[progress]` lines so planner/research/build do not look hung.

```bash
# edit conf.yaml, then:
uv run homelab-creator --run
```

## Session usage

```bash
uv run homelab-creator --run
```

Optional:

- `--thread-id` — checkpointer key (`[A-Za-z0-9_-]` only; default UUID)
- `--session-dir` — artifact directory (default `./sessions/<thread-id>/`)

Session dirs are **outside** `src/` (gitignored). They hold `spec.json`, `topology.md`, `writeup.md`, and `compose/`. The interview checkpoint is SQLite at `sessions/checkpoints.sqlite`.

Interactive TUI (default): DeepLabBuilder ASCII header + AskUserQuestion-style numbered menus (one question, labeled options). Combined form steps through vuln mode → difficulty → research → optional user vulns. HITL and worker failures use the same menu shape. Use `--plain` for the old line-input TUI (`key=value` form, typed actions). File HITL edit still supports path/body prompts. Compose up/down is approve/reject only. EOF is treated as stop.

After a successful plan, continue auto-builds (compose + topology + writeup) then HITL `lab_up`. Skip records `lab_up_status=skipped`; product success is a running lab or an explicit skip.

## Isolation

Generated Compose uses project bridge networks and **static IPv4**. There are **no** host `ports:` publishes. Reach services by lab network IP (for example `172.30.10.x` / `172.30.20.x`), not `localhost`. No `network_mode: host`, no `privileged`, no host binds outside the session dir.

`docker compose up` runs only for files under that session’s `compose/` after the isolation linter passes.

## Tests

```bash
uv run --extra dev pytest
```

Default CI has no live LLM. Optional markers: `docker` (compose CLI smoke), `llm`. Deselect with `-m "not docker and not llm"`.
