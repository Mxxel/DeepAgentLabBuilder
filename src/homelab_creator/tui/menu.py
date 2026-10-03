"""AskUserQuestion-style menus: one question, numbered options, optional free text."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MenuOption:
    """One numbered choice. ``value`` is what the menu returns when the option is picked."""

    value: Any
    label: str
    description: str = ""


class AskMenu:
    """Present a question with 2–N options (Cursor AskUserQuestion shape)."""

    def __init__(
        self,
        *,
        read: Callable[[], str],
        write: Callable[[str], None],
        style: Callable[[str, str], str] | None = None,
    ) -> None:
        self._read = read
        self._write = write
        self._style = style or (lambda text, _role: text)

    def ask(
        self,
        question: str,
        options: list[MenuOption],
        *,
        allow_other: bool = False,
        other_label: str = "Type something else",
        other_prompt: str = "Your answer",
    ) -> Any:
        if not options and not allow_other:
            raise ValueError("menu needs options")
        while True:
            self._write("\n")
            self._write(self._style(f"? {question}", "title") + "\n")
            for i, opt in enumerate(options, start=1):
                desc = f" — {opt.description}" if opt.description else ""
                line = f"  {i}. {opt.label}{desc}"
                self._write(self._style(line, "option") + "\n")
            other_idx = 0
            if allow_other:
                other_idx = len(options) + 1
                self._write(self._style(f"  {other_idx}. {other_label}", "option") + "\n")
            self._write(self._style("> ", "accent"))
            try:
                raw = self._read().strip()
            except EOFError:
                return None
            if not raw:
                continue
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(options):
                    return options[idx - 1].value
                if allow_other and idx == other_idx:
                    self._write(self._style(f"{other_prompt}: ", "accent"))
                    try:
                        typed = self._read().strip()
                    except EOFError:
                        return None
                    if typed:
                        return typed
                    continue
            # Allow typing the option value/label directly.
            lower = raw.lower()
            for opt in options:
                if str(opt.value).lower() == lower or opt.label.lower() == lower:
                    return opt.value
            if allow_other and raw:
                return raw
            self._write(self._style("Pick a number from the list.\n", "warn"))

    def ask_text(self, question: str, *, default: str = "") -> str:
        hint = f" [{default}]" if default else ""
        self._write("\n")
        self._write(self._style(f"? {question}{hint}", "title") + "\n")
        self._write(self._style("> ", "accent"))
        try:
            raw = self._read().strip()
        except EOFError:
            return default
        return raw if raw else default
