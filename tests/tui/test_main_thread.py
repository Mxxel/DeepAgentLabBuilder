from homelab_creator.__main__ import _default_session
from homelab_creator.tui.render import render


def test_thread_id_rejects_path():
    try:
        _default_session("/tmp/lab")
    except ValueError as exc:
        assert "thread-id" in str(exc)
    else:
        raise AssertionError("expected invalid thread-id")


def test_render_shows_writeup_body():
    text = render(
        {
            "interrupt_kind": "hitl_tool",
            "tool": "write_session_files",
            "args": {"files": {"writeup.md": "# Writeup\nweb app dc\n"}},
        }
    )
    assert "writeup.md" in text
    assert "# Writeup" in text
