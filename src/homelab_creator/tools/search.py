"""Tavily search backend (HITL-approved query). No exploit recipes."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from homelab_creator.spec.safety import contains_poc

SearchFn = Callable[[str], list[dict[str, Any]]]
TAVILY_URL = "https://api.tavily.com/search"
MAX_RESULTS = 8
SNIPPET_LEN = 400


class MissingSearchKeyError(Exception):
    """Raised when the search backend has no API key."""


class SearchDisabledError(Exception):
    """Raised when live HTTP search is not enabled."""


def search_api_key() -> str:
    """Tavily key from the environment, then ``search.api_key`` or ``tavily.api_key`` in ``conf.yaml``."""
    for env_name in ("HOMELAB_SEARCH_API_KEY", "TAVILY_API_KEY"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return env
    from homelab_creator.config import conf_path
    import yaml

    path = conf_path()
    if path is None:
        return ""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return ""
    for section in ("search", "tavily"):
        block = loaded.get(section)
        if not isinstance(block, dict):
            continue
        key = block.get("api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return ""


def parse_tavily(payload: object) -> list[dict[str, Any]]:
    """Normalize a Tavily JSON body into title/url/snippet hits, dropping deny-listed text."""
    if not isinstance(payload, dict):
        return []
    hits: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:SNIPPET_LEN]
        url = str(item.get("url") or "").strip()[:SNIPPET_LEN]
        snippet = str(item.get("content") or item.get("snippet") or "").strip()[:SNIPPET_LEN]
        blob = f"{title} {snippet} {url}"
        if contains_poc(blob):
            continue
        if not (title or snippet or url):
            continue
        hits.append({"title": title, "url": url, "snippet": snippet})
        if len(hits) >= MAX_RESULTS:
            break
    return hits


def tavily_search(query: str, api_key: str, *, opener: Callable | None = None) -> list[dict[str, Any]]:
    """POST one Tavily search. ``opener`` replaces ``urlopen`` in tests."""
    body = json.dumps({"query": query, "max_results": MAX_RESULTS, "search_depth": "basic"}).encode()
    req = urllib.request.Request(
        TAVILY_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError("tavily_failed") from exc
    return parse_tavily(raw)


def default_search(query: str) -> list[dict[str, Any]]:
    """Live Tavily search, or an error when heuristic mode or the API key is missing."""
    from homelab_creator.workers.llm import heuristic_forced

    if heuristic_forced():
        raise SearchDisabledError("heuristic mode: no live search")
    key = search_api_key()
    if not key:
        raise MissingSearchKeyError("missing Tavily API key (search.api_key in conf.yaml)")
    from homelab_creator.tui.progress import emit

    emit("Research: querying Tavily for public writeups (no exploit recipes).")
    return tavily_search(query, key)
