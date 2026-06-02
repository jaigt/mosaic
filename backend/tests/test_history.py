"""Tests for conversation-history formatting used to make /chat multi-turn aware."""
from backend.api.main import _format_history


def test_empty_history_returns_empty_string():
    assert _format_history([]) == ""


def test_formats_user_and_assistant_turns_in_order():
    history = [
        {"role": "user", "content": "What was Apple's revenue in 2023?"},
        {"role": "assistant", "content": "Apple reported $383B in revenue."},
    ]
    out = _format_history(history)
    assert "User: What was Apple's revenue in 2023?" in out
    assert "Assistant: Apple reported $383B in revenue." in out
    # Order preserved: user turn appears before assistant turn.
    assert out.index("User:") < out.index("Assistant:")


def test_keeps_only_the_last_n_turns():
    history = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
    out = _format_history(history, max_turns=6)
    assert "msg19" in out
    assert "msg14" in out
    # The 7th-from-last and older are dropped.
    assert "msg13" not in out
    assert "msg0" not in out


def test_truncates_overlong_content():
    history = [{"role": "user", "content": "x" * 5000}]
    out = _format_history(history, max_chars=100)
    assert "x" * 100 in out
    assert "x" * 200 not in out


def test_skips_malformed_or_empty_entries():
    history = [
        {"role": "user"},  # missing content
        {"content": "no role"},  # missing role
        {"role": "user", "content": "   "},  # whitespace only
        {"role": "user", "content": "real question"},
        "not a dict",
    ]
    out = _format_history(history)
    assert out.strip() == "User: real question"


def test_excludes_the_current_message_when_it_is_last_user_turn():
    # The frontend appends the just-sent user message to history before sending.
    # We pass the live message separately, so the trailing duplicate must be dropped.
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "current question"},
    ]
    out = _format_history(history, current_message="current question")
    assert "first question" in out
    assert "first answer" in out
    assert "current question" not in out
