"""Tests for the multi-tool ReAct evidence-gathering loop.

``parse_action`` and the prompt builders are pure; ``ReactAgent.run`` is driven
with injected fakes (no network/LLM) and a scripted ``generate_fn`` that returns
one JSON action per step.
"""
import json
from types import SimpleNamespace

import pytest

from backend.agent.react import (
    Action,
    ReactAgent,
    build_step_prompt,
    build_system_prompt,
    parse_action,
)


# ── parse_action (pure) ───────────────────────────────────────────────────────

def test_parse_plain_json():
    a = parse_action('{"thought":"look","tool":"search_filings","input":{"query":"revenue"}}')
    assert a.tool == "search_filings"
    assert a.input == {"query": "revenue"}
    assert a.thought == "look"
    assert a.parse_ok


def test_parse_code_fenced_and_prose():
    raw = 'Sure!\n```json\n{"tool":"answer","input":{}}\n```'
    a = parse_action(raw)
    assert a.tool == "answer" and a.parse_ok


def test_parse_garbage_returns_answer_not_ok():
    a = parse_action("I will now search the filings.")
    assert a.tool == "answer"
    assert a.parse_ok is False


def test_parse_missing_tool_defaults_answer():
    a = parse_action('{"thought":"done"}')
    assert a.tool == "answer"


def test_parse_non_dict_input_coerced():
    a = parse_action('{"tool":"list_corpus","input":"oops"}')
    assert a.input == {}


def test_prompts_are_strings():
    assert "JSON" in build_system_prompt()
    p = build_step_prompt("What is AAPL revenue?", [{"role": "user", "content": "hi"}], ["Action: x\nObservation: y"])
    assert "USER QUESTION" in p and "STEPS SO FAR" in p


# ── ReactAgent.run (injected fakes) ───────────────────────────────────────────

def _rc(chunk_id, ticker="AAPL", section="Item 7: MD&A"):
    chunk = SimpleNamespace(
        chunk_id=chunk_id, ticker=ticker, document_type="10-K", filing_year=2024,
        filing_quarter="FY", sec_item_section=section, chunk_type="text",
        text_content=f"content {chunk_id}", raw_payload="raw",
    )
    return SimpleNamespace(chunk=chunk, score=0.9)


def _scripted_generate(*actions):
    """Return a generate_fn that emits the given JSON actions in order."""
    seq = iter(actions)

    def gen(prompt, model):
        try:
            return json.dumps(next(seq))
        except StopIteration:
            return json.dumps({"tool": "answer", "input": {}})
    return gen


def _agent(generate_fn, *, retrieve_fn=None, ingest_fn=None, list_fn=None, max_steps=5):
    return ReactAgent(
        generate_fn=generate_fn,
        retrieve_fn=retrieve_fn or (lambda **kw: []),
        ingest_fn=ingest_fn or (lambda **kw: 0),
        list_corpus_fn=list_fn or (lambda: "Corpus: AAPL 10-K 2024"),
        model="test-model",
        max_steps=max_steps,
    )


def test_search_then_answer_accumulates_sources():
    gen = _scripted_generate(
        {"tool": "search_filings", "input": {"query": "net revenue", "ticker": "AAPL"}},
        {"tool": "answer", "input": {}},
    )
    retrieved = [_rc("c1"), _rc("c2")]
    events = []
    agent = _agent(gen, retrieve_fn=lambda **kw: retrieved)
    result = agent.run("What was AAPL revenue?", [], {}, events.append)

    assert result.ready_reason == "answered"
    assert [c.chunk.chunk_id for c in result.sources] == ["c1", "c2"]
    assert any(e["kind"] == "search" for e in events)


def test_ingest_when_search_empty_then_finds():
    """Empty search → ingest → search again returns results → answer."""
    gen = _scripted_generate(
        {"tool": "search_filings", "input": {"query": "NVDA revenue", "ticker": "NVDA"}},
        {"tool": "ingest_filing", "input": {"ticker": "NVDA"}},
        {"tool": "search_filings", "input": {"query": "NVDA revenue", "ticker": "NVDA"}},
        {"tool": "answer", "input": {}},
    )
    search_calls = {"n": 0}

    def fake_retrieve(**kw):
        search_calls["n"] += 1
        return [] if search_calls["n"] == 1 else [_rc("n1", ticker="NVDA")]

    ingests = []
    events = []
    agent = _agent(
        gen, retrieve_fn=fake_retrieve,
        ingest_fn=lambda **kw: ingests.append(kw) or 42,
    )
    result = agent.run("How is NVDA doing?", [], {}, events.append)

    assert ingests == [{"ticker": "NVDA", "document_type": "10-K", "year": None}]
    assert [c.chunk.chunk_id for c in result.sources] == ["n1"]
    kinds = [e["kind"] for e in events]
    assert "ingest" in kinds and "ingest_done" in kinds


def test_dedupes_sources_across_searches():
    gen = _scripted_generate(
        {"tool": "search_filings", "input": {"query": "q1"}},
        {"tool": "search_filings", "input": {"query": "q2"}},
        {"tool": "answer", "input": {}},
    )
    # Both searches return overlapping chunk c1; c1 must appear once.
    agent = _agent(gen, retrieve_fn=lambda **kw: [_rc("c1"), _rc("c2")])
    result = agent.run("q", [], {}, lambda e: None)
    ids = [c.chunk.chunk_id for c in result.sources]
    assert ids == ["c1", "c2"]


def test_repeated_identical_action_stops_loop():
    # Same action forever — the loop guard must stop after the repeat.
    same = {"tool": "search_filings", "input": {"query": "same"}}
    gen = _scripted_generate(same, same, same, same, same)
    calls = {"n": 0}
    agent = _agent(gen, retrieve_fn=lambda **kw: (calls.__setitem__("n", calls["n"] + 1), [_rc("c1")])[1])
    result = agent.run("q", [], {}, lambda e: None)
    assert result.ready_reason == "answered"
    assert calls["n"] == 1   # executed once, second identical action broke the loop


def test_max_steps_cap():
    # Model keeps searching with DIFFERENT queries; must stop at max_steps.
    gen = lambda prompt, model: json.dumps(
        {"tool": "search_filings", "input": {"query": f"q{prompt.count('Observation')}"}}
    )
    agent = _agent(gen, retrieve_fn=lambda **kw: [_rc("c1")], max_steps=3)
    result = agent.run("q", [], {}, lambda e: None)
    assert result.ready_reason == "max_steps"
    assert result.steps == 3


def test_generate_failure_ends_gracefully():
    def boom(prompt, model):
        raise RuntimeError("429 quota")

    agent = _agent(boom)
    result = agent.run("q", [], {}, lambda e: None)
    assert result.ready_reason == "parse_error"
    assert result.sources == []


def test_explicit_filters_seed_search_when_model_omits():
    seen = {}

    def fake_retrieve(**kw):
        seen.update(kw)
        return [_rc("c1")]

    gen = _scripted_generate(
        {"tool": "search_filings", "input": {"query": "revenue"}},  # no ticker
        {"tool": "answer", "input": {}},
    )
    agent = _agent(gen, retrieve_fn=fake_retrieve)
    agent.run("q", [], {"ticker": "MSFT", "year": 2023, "document_type": "10-K"}, lambda e: None)
    assert seen["ticker"] == "MSFT" and seen["year"] == 2023
