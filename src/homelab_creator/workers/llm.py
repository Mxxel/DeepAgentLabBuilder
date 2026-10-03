"""Chat model: OpenAI-compatible API via airouter.ch (Chat Completions)."""

from __future__ import annotations

import os

from homelab_creator.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_settings

class MissingModelError(RuntimeError):
    """No API key; heuristic workers should run instead."""


def api_key() -> str:
    """Chat API key from ``conf.yaml`` or the environment. Empty when unset."""
    return load_settings().api_key


def base_url() -> str:
    """OpenAI-compatible base URL. Defaults to the airouter.ch v1 endpoint."""
    return load_settings().base_url


def model_id() -> str:
    """Chat model id from settings. Defaults to ``Qwen3.8``."""
    return load_settings().model


def reasoning_effort() -> str:
    """Reasoning effort sent to airouter.ch. Defaults to ``medium``."""
    return load_settings().reasoning_effort


def heuristic_forced() -> bool:
    """True when ``HOMELAB_HEURISTIC`` forces catalog fills and blocks live search."""
    return os.environ.get("HOMELAB_HEURISTIC", "").strip().lower() in {"1", "true", "yes"}


def live_llm_enabled() -> bool:
    """True when a chat key is configured and heuristic mode is off."""
    if heuristic_forced():
        return False
    return bool(api_key())


def chat_model():
    """LangChain ChatOpenAI pointed at airouter.ch.

    ``reasoning_effort`` is sent in extra_body so airouter.ch keeps the
    OpenAI-compatible field name (not OpenAI's nested ``reasoning.effort``).
    """
    settings = load_settings()
    if not settings.api_key:
        raise MissingModelError("set airouter.api_key in conf.yaml")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=180,
        max_retries=0,
        extra_body={"reasoning_effort": settings.reasoning_effort},
    )
