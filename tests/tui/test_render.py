from homelab_creator.spec.safety import contains_poc
from homelab_creator.tui.render import BANNER, render


def test_render_all_interrupt_kinds():
    kinds = [
        "offer_idea",
        "ask_stop",
        "choose_next_move",
        "combined_form",
        "extend_chain",
        "ask_extra_paths",
        "lab_up",
        "hitl_tool",
        "worker_budget",
    ]
    for kind in kinds:
        text = render({"interrupt_kind": kind, "allowed": ["x"], "tool": "search", "args": {"query": "creds"}})
        assert BANNER in text
        assert f"[{kind}]" in text
        assert not contains_poc(text)


def test_render_redacts_poc_and_lists_hosts():
    text = render(
        {"interrupt_kind": "offer_idea", "suggestions": ["payload: not shown"]},
        hosts=[{"id": "web", "role": "foothold"}],
    )
    assert "[redacted]" in text
    assert "web (foothold)" in text
    assert "payload:" not in text.lower() or "[redacted]" in text


def test_render_search_hitl_explains_tavily():
    text = render({"interrupt_kind": "hitl_tool", "tool": "search", "args": {"query": "public pentest"}, "allowed": ["approve"]})
    assert "Tavily" in text
    assert "search.api_key" in text


def test_render_combined_form_explains_fields():
    text = render({"interrupt_kind": "combined_form", "allowed": ["submit"], "fields": ["vuln_mode", "difficulty", "research.opted_in", "user_vulns"]})
    assert "vuln_mode  user | agent | both" in text
    assert "difficulty  beginner |" in text
    assert "research.opted_in  true | false" in text
    assert "user_vulns  name|" in text
    assert "Empty input submits" in text
    assert "example:" in text
    assert "Who authors lab issues" in text
