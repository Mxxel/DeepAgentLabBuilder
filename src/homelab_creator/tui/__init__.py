"""TUI package: interrupt renderer + headless/stdio/interactive adapters."""

from homelab_creator.tui.headless import PAUSE, ScriptedTUI
from homelab_creator.tui.render import BANNER, render
from homelab_creator.tui.stdio import StdioTUI

__all__ = ["BANNER", "PAUSE", "InteractiveTUI", "ScriptedTUI", "StdioTUI", "render", "run_session"]


def __getattr__(name: str):
    if name == "InteractiveTUI":
        from homelab_creator.tui.interactive import InteractiveTUI

        return InteractiveTUI
    if name == "run_session":
        from homelab_creator.tui.session import run_session

        return run_session
    raise AttributeError(name)
