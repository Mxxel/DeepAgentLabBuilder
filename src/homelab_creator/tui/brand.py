"""DeepLabBuilder brand: ASCII header and terminal theme tokens."""

from __future__ import annotations

# Industrial night-ops look: cool cyan + warm amber on charcoal (not purple/cream).
THEME = {
    "header": "bold cyan",
    "rule": "bright_black",
    "title": "bold bright_white",
    "muted": "bright_black",
    "accent": "bold yellow",
    "ok": "bold green",
    "warn": "bold red",
    "option": "cyan",
    "progress": "yellow",
    "panel_border": "cyan",
}

ASCII_HEADER = r"""
 ____                 _          _           ____        _ _     _
|  _ \  ___  ___ _ __| |    __ _| |__       | __ ) _   _(_) | __| | ___ _ __
| | | |/ _ \/ _ \ '_ \ |   / _` | '_ \ _____|  _ \| | | | | |/ _` |/ _ \ '__|
| |_| |  __/  __/ |_) | |__| (_| | |_) |_____| |_) | |_| | | | (_| |  __/ |
|____/ \___|\___| .__/|_____\__,_|_.__/      |____/ \__,_|_|_|\__,_|\___|_|
                |_|
""".strip("\n")

TAGLINE = "Pwn the company — isolated assessment labs (no exploit recipes in this TUI)."


def header_block() -> str:
    """ASCII wordmark plus the assessment tagline, for the interactive header."""
    return f"{ASCII_HEADER}\n{TAGLINE}"
