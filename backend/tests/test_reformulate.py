"""Tests for history-aware query reformulation (condense-question).

All logic under test is pure (no network / no LLM call). The prompt builder and
the skip-decision heuristic are exercised directly; the LLM-backed
``condense_query`` is exercised with an injected fake model fn so no API key is
needed.
"""
from backend.retrieval.reformulate import (
    build_condense_prompt,
    should_reformulate,
    condense_query,
)


# ── should_reformulate (pure heuristic) ──────────────────────────────────────

def test_skip_when_no_history():
    assert should_reformulate([], "what about margins?") is False


def test_reformulate_with_history_and_short_followup():
    history = [
        {"role": "user", "content": "What was Apple's revenue in 2023?"},
        {"role": "assistant", "content": "Apple reported $383B."},
    ]
    assert should_reformulate(history, "what about margins?") is True


def test_skip_when_message_contains_ticker():
    history = [{"role": "user", "content": "Tell me about Apple."}]
    # A message naming a concrete ticker is already self-contained.
    assert should_reformulate(history, "What were AAPL gross margins?") is False


def test_skip_when_message_is_long_and_self_contained():
    history = [{"role": "user", "content": "Tell me about Apple."}]
    long_msg = (
        "Please summarize the operating margin trend for the company across the "
        "last three fiscal years and explain the primary drivers behind any change."
    )
    assert should_reformulate(history, long_msg) is False


def test_skip_on_empty_message():
    history = [{"role": "user", "content": "x"}]
    assert should_reformulate(history, "   ") is False


# ── build_condense_prompt (pure) ─────────────────────────────────────────────

def test_prompt_includes_history_and_message():
    history = [
        {"role": "user", "content": "What was Apple's revenue in 2023?"},
        {"role": "assistant", "content": "Apple reported $383B."},
    ]
    prompt = build_condense_prompt(history, "what about margins?")
    assert "What about margins?".lower() in prompt.lower() or "what about margins?" in prompt
    assert "revenue in 2023" in prompt
    assert "$383B" in prompt
    # Must instruct the model to return a standalone question.
    assert "standalone" in prompt.lower()


def test_prompt_orders_turns_and_labels_roles():
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    prompt = build_condense_prompt(history, "third")
    assert prompt.index("first") < prompt.index("second")
    assert "User:" in prompt and "Assistant:" in prompt


def test_prompt_skips_malformed_history_entries():
    history = [
        {"role": "user"},  # no content
        "not a dict",
        {"role": "user", "content": "real turn"},
    ]
    prompt = build_condense_prompt(history, "follow up")
    assert "real turn" in prompt


# ── condense_query (thin LLM wrapper, fake model injected) ────────────────────

def test_condense_query_skips_llm_when_heuristic_says_no():
    calls = []

    def fake_model(prompt: str, model: str) -> str:
        calls.append(prompt)
        return "SHOULD NOT BE CALLED"

    out = condense_query([], "standalone question here", model_fn=fake_model)
    assert out == "standalone question here"
    assert calls == []  # no LLM call


def test_condense_query_calls_llm_and_returns_standalone():
    history = [
        {"role": "user", "content": "What was Apple's revenue in 2023?"},
        {"role": "assistant", "content": "Apple reported $383B."},
    ]

    def fake_model(prompt: str, model: str) -> str:
        assert "revenue in 2023" in prompt
        return "What were Apple's gross margins in 2023?"

    out = condense_query(history, "what about margins?", model_fn=fake_model)
    assert out == "What were Apple's gross margins in 2023?"


def test_condense_query_falls_back_to_original_on_llm_error():
    history = [
        {"role": "user", "content": "What was Apple's revenue in 2023?"},
        {"role": "assistant", "content": "Apple reported $383B."},
    ]

    def boom(prompt: str, model: str) -> str:
        raise RuntimeError("invalid api key")

    out = condense_query(history, "what about margins?", model_fn=boom)
    assert out == "what about margins?"


def test_condense_query_falls_back_when_llm_returns_empty():
    history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]

    def empty(prompt: str, model: str) -> str:
        return "   "

    out = condense_query(history, "what about margins?", model_fn=empty)
    assert out == "what about margins?"
