"""Unit tests for the agent's pure decision logic and verification parsing."""
import pytest

from backend.agent.planner import (
    IngestPlan,
    VerificationResult,
    plan_auto_ingest,
    build_verification_prompt,
    parse_verification,
    verify_answer,
)


class _Chunk:
    def __init__(self, ticker):
        self.chunk = type("C", (), {"ticker": ticker})()


class _Retrieved:
    def __init__(self, ticker):
        self.chunk = type("C", (), {"ticker": ticker})()


def _chunks(*tickers):
    return [_Retrieved(t) for t in tickers]


# ── plan_auto_ingest ─────────────────────────────────────────────────────────

def test_no_plan_without_a_requested_ticker():
    # We never guess a ticker the user didn't name.
    assert plan_auto_ingest(None, None, None, _chunks("AAPL")) is None
    assert plan_auto_ingest("", None, None, []) is None


def test_no_plan_when_ticker_already_present():
    assert plan_auto_ingest("AAPL", "10-K", None, _chunks("AAPL", "MSFT")) is None
    # Case-insensitive match.
    assert plan_auto_ingest("aapl", None, None, _chunks("AAPL")) is None


def test_plan_when_requested_ticker_missing():
    plan = plan_auto_ingest("NVDA", None, None, _chunks("AAPL"))
    assert isinstance(plan, IngestPlan)
    assert plan.ticker == "NVDA"
    assert plan.document_type == "10-K"  # default
    assert plan.year is None


def test_plan_when_retrieval_empty():
    plan = plan_auto_ingest("TSLA", "10-Q", 2023, [])
    assert plan.ticker == "TSLA"
    assert plan.document_type == "10-Q"
    assert plan.year == 2023


def test_plan_clamps_non_ingestable_doc_type():
    # 8-K isn't supported by ingest_filing → clamp to the annual report.
    plan = plan_auto_ingest("NVDA", "8-K", None, [])
    assert plan.document_type == "10-K"


def test_ingest_plan_label():
    assert IngestPlan("NVDA", "10-K", 2024).label == "NVDA 10-K (2024)"
    assert IngestPlan("NVDA", "10-Q").label == "NVDA 10-Q (latest)"


# ── verification parsing ───────────────────────────────────────────────────────

def test_parse_supported():
    r = parse_verification('{"supported": true, "issues": []}')
    assert r.status == "supported"
    assert r.issues == []


def test_parse_caveats_from_issues():
    r = parse_verification('{"supported": false, "issues": ["Revenue figure not in sources"]}')
    assert r.status == "caveats"
    assert r.issues == ["Revenue figure not in sources"]


def test_parse_caveats_when_supported_true_but_issues_present():
    # Contradictory model output: issues win (be conservative).
    r = parse_verification('{"supported": true, "issues": ["margin claim unverified"]}')
    assert r.status == "caveats"


def test_parse_strips_code_fences_and_prose():
    raw = 'Here is my analysis:\n```json\n{"supported": true, "issues": []}\n```'
    assert parse_verification(raw).status == "supported"


def test_parse_garbage_is_unknown():
    assert parse_verification("not json at all").status == "unknown"
    assert parse_verification("").status == "unknown"


def test_build_verification_prompt_truncates_sources():
    prompt = build_verification_prompt("answer", "x" * 20000, source_limit=100)
    assert "x" * 100 in prompt
    assert "x" * 101 not in prompt


# ── verify_answer wrapper ──────────────────────────────────────────────────────

def test_verify_answer_empty_is_unknown():
    assert verify_answer("", "sources").status == "unknown"


def test_verify_answer_uses_injected_model_fn():
    calls = []

    def fake(prompt, model):
        calls.append((prompt, model))
        return '{"supported": true, "issues": []}'

    r = verify_answer("Apple revenue was $391B.", "SOURCES...", model_fn=fake, model="m")
    assert r.status == "supported"
    assert calls and calls[0][1] == "m"


def test_verify_answer_swallows_llm_failure():
    def boom(prompt, model):
        raise RuntimeError("rate limit")

    assert verify_answer("answer", "sources", model_fn=boom, model="m").status == "unknown"
