"""Tests for the pure retrieval-eval metrics and the harness orchestration
(with an injected fake retriever — no network/LLM)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.eval.metrics import (
    EvalCase,
    build_report,
    case_matches,
    hit_at_k,
    rank_of_first_match,
    reciprocal_rank,
)
from backend.eval.harness import run_eval, load_eval_set, format_report


def _chunk(ticker, section="Item 7: MD&A", doc_type="10-K", year=2024):
    return SimpleNamespace(
        ticker=ticker, sec_item_section=section,
        document_type=doc_type, filing_year=year,
    )


def _retrieved(*chunks):
    return [SimpleNamespace(chunk=c, score=0.5) for c in chunks]


# ── matching ───────────────────────────────────────────────────────────────

def test_case_matches_ticker_only():
    case = EvalCase(query="q", ticker="AAPL")
    assert case_matches(case, _chunk("AAPL"))
    assert not case_matches(case, _chunk("MSFT"))


def test_case_matches_section_substring_case_insensitive():
    case = EvalCase(query="q", ticker="AAPL", section_contains="risk")
    assert case_matches(case, _chunk("AAPL", section="Item 1A: Risk Factors"))
    assert not case_matches(case, _chunk("AAPL", section="Item 7: MD&A"))


def test_case_matches_doc_type_and_year():
    case = EvalCase(query="q", ticker="AAPL", doc_type="10-Q", year=2023)
    assert case_matches(case, _chunk("AAPL", doc_type="10-Q", year=2023))
    assert not case_matches(case, _chunk("AAPL", doc_type="10-K", year=2023))
    assert not case_matches(case, _chunk("AAPL", doc_type="10-Q", year=2024))


# ── ranking metrics ──────────────────────────────────────────────────────────

def test_rank_of_first_match():
    case = EvalCase(query="q", ticker="AAPL", section_contains="Risk")
    retrieved = _retrieved(
        _chunk("MSFT", section="Risk Factors"),       # wrong ticker
        _chunk("AAPL", section="Item 7: MD&A"),        # wrong section
        _chunk("AAPL", section="Item 1A: Risk Factors"),  # match at rank 3
    )
    assert rank_of_first_match(case, retrieved) == 3
    assert hit_at_k(case, retrieved, 3)
    assert not hit_at_k(case, retrieved, 2)
    assert reciprocal_rank(case, retrieved) == pytest.approx(1 / 3)


def test_no_match_metrics():
    case = EvalCase(query="q", ticker="NVDA")
    retrieved = _retrieved(_chunk("AAPL"), _chunk("MSFT"))
    assert rank_of_first_match(case, retrieved) is None
    assert not hit_at_k(case, retrieved, 5)
    assert reciprocal_rank(case, retrieved) == 0.0


def test_report_aggregates():
    cases = [EvalCase("q1", "AAPL"), EvalCase("q2", "MSFT"), EvalCase("q3", "NVDA")]
    retrieved = [
        _retrieved(_chunk("AAPL")),                       # rank 1
        _retrieved(_chunk("AAPL"), _chunk("MSFT")),       # rank 2
        _retrieved(_chunk("AAPL"), _chunk("MSFT")),       # no match
    ]
    report = build_report(cases, retrieved)
    assert report.n == 3
    # Use the unrounded accessors; summary() rounds for display.
    assert report.hit_rate_at(1) == pytest.approx(1 / 3)   # only the first
    assert report.hit_rate_at(3) == pytest.approx(2 / 3)   # first two
    assert report.mrr == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    assert report.summary()["n"] == 3


def test_build_report_length_mismatch_raises():
    with pytest.raises(ValueError):
        build_report([EvalCase("q", "AAPL")], [])


# ── harness orchestration with an injected retriever ──────────────────────────

def test_run_eval_uses_injected_retriever_and_passes_filters():
    cases = [EvalCase(query="revenue?", ticker="AAPL", doc_type="10-K", year=2024)]
    seen = {}

    def fake_retrieve(query, top_k, ticker, year, document_type):
        seen.update(dict(query=query, top_k=top_k, ticker=ticker,
                         year=year, document_type=document_type))
        return _retrieved(_chunk("AAPL"))

    report = run_eval(cases, retrieve_fn=fake_retrieve, top_k=5)
    assert seen == dict(query="revenue?", top_k=5, ticker="AAPL",
                        year=2024, document_type="10-K")
    assert report.hit_rate_at(1) == 1.0


def test_seed_eval_set_loads():
    cases = load_eval_set(Path("backend/eval/eval_set.json"))
    assert len(cases) >= 5
    assert all(c.query and c.ticker for c in cases)


def test_format_report_is_stringable():
    cases = [EvalCase("q1", "AAPL")]
    report = build_report(cases, [_retrieved(_chunk("AAPL"))])
    text = format_report(report)
    assert "MRR" in text and "hit@1" in text
