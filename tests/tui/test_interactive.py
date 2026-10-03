from homelab_creator.tui.brand import ASCII_HEADER, TAGLINE, header_block
from homelab_creator.tui.interactive import InteractiveTUI
from homelab_creator.tui.menu import AskMenu, MenuOption


def test_ascii_header_contains_brand():
    text = header_block()
    assert "DeepLab" in ASCII_HEADER or "___" in ASCII_HEADER
    assert "Pwn the company" in TAGLINE
    assert TAGLINE in text


def test_ask_menu_numbered_choice():
    answers = iter(["2"])
    out: list[str] = []
    menu = AskMenu(read=lambda: next(answers), write=out.append)
    value = menu.ask(
        "Continue?",
        [
            MenuOption("continue", "continue", "Keep going"),
            MenuOption("stop", "stop", "End session"),
        ],
    )
    assert value == "stop"
    joined = "".join(out)
    assert "? Continue?" in joined
    assert "1. continue" in joined
    assert "2. stop" in joined


def test_interactive_ask_stop_menu():
    answers = iter(["1"])
    out: list[str] = []
    tui = InteractiveTUI(read=lambda: next(answers), write=out.append, use_rich=False)
    resume = tui.show({"interrupt_kind": "ask_stop", "allowed": ["continue", "stop"]})
    assert resume == "continue"
    joined = "".join(out)
    assert "DeepLabBuilder" in joined or "___" in joined
    assert "Continue the interview" in joined


def test_interactive_combined_form_steps():
    # agent, beginner, no research
    answers = iter(["2", "1", "1"])
    out: list[str] = []
    tui = InteractiveTUI(read=lambda: next(answers), write=out.append, use_rich=False)
    resume = tui.show({"interrupt_kind": "combined_form", "allowed": ["submit"]})
    assert resume["action"] == "submit"
    assert resume["vuln_mode"] == "agent"
    assert resume["difficulty"] == "beginner"
    assert resume["research.opted_in"] is False


def test_interactive_offer_idea_pick():
    answers = iter(["1"])
    tui = InteractiveTUI(read=lambda: next(answers), write=lambda _t: None, use_rich=False)
    resume = tui.show(
        {
            "interrupt_kind": "offer_idea",
            "suggestions": ["clinic network", "fintech"],
            "allowed": ["free_text", "pick"],
        }
    )
    assert resume == {"pick": 0}
