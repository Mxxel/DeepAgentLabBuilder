# Changelog

All notable changes to homelab-creator are recorded here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Docstrings on the public modules, types, and functions in `src/homelab_creator`.
- Code map in `docs/code.md`.
- ADR 0001 for the LangGraph session loop and Deep Agent workers.

## [0.1.0] - 2026-10-03

### Added

- Interview TUI (`homelab-creator --run`) that co-designs an isolated assessment lab. The session ends only when the operator confirms stop.
- LangGraph outer graph: idea, stop, next move, combined form, research, planner, extend-chain, extra paths, lab build, writeup, and lab up.
- Deep Agent workers for research notes and plan refinement, with catalog heuristics when no chat model is configured.
- Catalog Compose and topology for `foothold`, `internal`, and `crown_jewel`, plus optional `workstation`, `mail`, and `jump`. Static lab IPv4 on project bridge networks, with no host port publishes.
- Human approval before web search, session file writes, and `docker compose` up/down.
- Plan-ready and artifact-ready checks, including an isolation linter.
- SQLite checkpoints at `sessions/checkpoints.sqlite`, keyed by `thread_id`.
- Chat settings for airouter.ch in `conf.yaml`, and optional Tavily research via `search.api_key`.
