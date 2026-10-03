"""Load airouter.ch settings from conf.yaml (cwd or HOMELAB_CONF)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_BASE_URL = "https://api.airouter.ch/v1"
DEFAULT_MODEL = "Qwen3.8"
DEFAULT_REASONING = "medium"
ALLOWED_REASONING = frozenset({"none", "low", "medium", "high", "xhigh"})


@dataclass(frozen=True)
class AirouterSettings:
    """Chat endpoint, key, model, and reasoning effort after defaults are applied."""

    api_key: str
    model: str
    reasoning_effort: str
    base_url: str
    path: Path | None


def conf_path() -> Path | None:
    """Locate ``conf.yaml`` via ``HOMELAB_CONF``, the working directory, then the repo root."""
    raw = os.environ.get("HOMELAB_CONF", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_file() else None
    cwd = Path.cwd() / "conf.yaml"
    if cwd.is_file():
        return cwd
    root = Path(__file__).resolve().parents[2] / "conf.yaml"
    if root.is_file():
        return root
    return None


def _section(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    block = raw.get("airouter")
    if isinstance(block, dict):
        return block
    return raw if any(k in raw for k in ("api_key", "model", "reasoning_effort")) else {}


def _str(block: dict, *keys: str) -> str:
    for key in keys:
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_settings() -> AirouterSettings:
    """Load chat settings from YAML, then environment variables, then built-in defaults.

    An empty file key falls back to ``AIROUTER_API_KEY`` or ``OPENAI_API_KEY``.
    Unknown ``reasoning_effort`` values become ``medium``.
    """
    path = conf_path()
    block: dict = {}
    if path is not None:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        block = _section(loaded)
    effort = (
        _str(block, "reasoning_effort", "reasoning")
        or os.environ.get("HOMELAB_REASONING_EFFORT", "").strip()
        or DEFAULT_REASONING
    ).lower()
    if effort not in ALLOWED_REASONING:
        effort = DEFAULT_REASONING
    return AirouterSettings(
        api_key=_str(block, "api_key", "key")
        or os.environ.get("AIROUTER_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip(),
        model=_str(block, "model")
        or os.environ.get("HOMELAB_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or DEFAULT_MODEL,
        reasoning_effort=effort,
        base_url=_str(block, "base_url")
        or os.environ.get("AIROUTER_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or os.environ.get("OPENAI_API_BASE", "").strip()
        or DEFAULT_BASE_URL,
        path=path,
    )
