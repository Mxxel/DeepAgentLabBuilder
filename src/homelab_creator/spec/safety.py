"""Shared deny-list for writeup and research text."""

from __future__ import annotations

POC_MARKERS = ("exploitpoc", "stepbystepexploit", "payload:")


def normalize_text(text: str) -> str:
    """Lowercase and drop quotes, spaces, and hyphens before the deny-list check."""
    cleaned = text.lower()
    for ch in ('"', "'", " ", "\t", "-"):
        cleaned = cleaned.replace(ch, "")
    return cleaned


def contains_poc(text: str) -> bool:
    """True when text matches the coarse exploit-recipe deny-list."""
    blob = normalize_text(text)
    return any(marker in blob for marker in POC_MARKERS)
