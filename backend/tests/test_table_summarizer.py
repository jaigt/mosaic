"""
Tests for batched table summarization (``summarize_tables``): the delimiter
parse, the count-mismatch fallback to per-table calls, and the single-table
short-circuit. The LLM ``generate`` call is monkeypatched — no network.
"""
import pytest

import backend.pipeline.table_summarizer as ts


def test_batch_splits_on_delimiter(monkeypatch):
    """A well-formed delimited response is split into per-table summaries."""
    tables = ["<table>A</table>", "<table>B</table>", "<table>C</table>"]

    def fake_generate(prompt, model):
        # Model returns N summaries joined by the documented delimiter.
        return f" SUM-A {ts._BATCH_DELIM} SUM-B {ts._BATCH_DELIM} SUM-C "

    monkeypatch.setattr(ts, "generate", fake_generate)
    out = ts.summarize_tables(tables, ticker="AAPL", document_type="10-K")
    assert out == ["SUM-A", "SUM-B", "SUM-C"]


def test_batch_count_mismatch_falls_back_to_per_table(monkeypatch):
    """If the batched response has the wrong number of parts, fall back to
    one call per table so the result is always correct."""
    tables = ["<table>A</table>", "<table>B</table>", "<table>C</table>"]
    calls = {"batch": 0, "single": []}

    def fake_generate(prompt, model):
        # Distinguish the batch call (mentions multiple TABLE markers) from the
        # per-table fallback calls (single table prompt).
        if "### TABLE 2" in prompt:
            calls["batch"] += 1
            return "only-one-summary-no-delimiter"  # wrong count → triggers fallback
        calls["single"].append(prompt)
        return "PER-TABLE-SUMMARY"

    monkeypatch.setattr(ts, "generate", fake_generate)
    out = ts.summarize_tables(tables, ticker="AAPL", document_type="10-K")

    assert calls["batch"] == 1
    assert len(calls["single"]) == 3  # one fallback call per table
    assert out == ["PER-TABLE-SUMMARY"] * 3


def test_single_table_uses_single_path(monkeypatch):
    """A one-element batch short-circuits to the single-table summarizer."""
    seen = {}

    def fake_generate(prompt, model):
        seen["prompt"] = prompt
        return "SOLO"

    monkeypatch.setattr(ts, "generate", fake_generate)
    out = ts.summarize_tables(["<table>X</table>"], ticker="AAPL", document_type="10-K")
    assert out == ["SOLO"]
    # The single path uses the non-batch prompt (no delimiter instruction).
    assert ts._BATCH_DELIM not in seen["prompt"]


def test_empty_list_returns_empty(monkeypatch):
    monkeypatch.setattr(ts, "generate", lambda prompt, model: "should-not-be-called")
    assert ts.summarize_tables([], ticker="AAPL", document_type="10-K") == []
