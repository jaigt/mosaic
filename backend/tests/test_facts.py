"""Tests for the structured financial fact base (taxonomy / extractor / store /
validator). All pure — no network, no model."""
import pandas as pd
import pytest

from backend.facts import store
from backend.facts.extractor import facts_from_frames, parse_period
from backend.facts.models import FinancialFact, FilingRef
from backend.facts.taxonomy import map_concept
from backend.facts.validator import validate_period, flag_low_confidence


# ── taxonomy ──────────────────────────────────────────────────────────────────

def test_map_concept_namespace_insensitive():
    assert map_concept("us-gaap:Revenues")[0] == "revenue"
    assert map_concept("Revenues")[0] == "revenue"
    assert map_concept("ifrs-full:Revenues")[0] == "revenue"  # any namespace


def test_taxonomy_covers_bank_revenue():
    # Banks' top line maps to revenue, but ranks BELOW the standard concept so a
    # normal filer is never mis-mapped.
    assert map_concept("us-gaap:RevenuesNetOfInterestExpense")[0] == "revenue"
    assert (map_concept("RevenueFromContractWithCustomerExcludingAssessedTax")[2]
            < map_concept("RevenuesNetOfInterestExpense")[2])
    assert map_concept("us-gaap:InterestIncomeExpenseNet")[0] == "net_interest_income"
    assert map_concept("us-gaap:NoninterestIncome")[0] == "noninterest_income"


def test_map_concept_unknown_is_none():
    assert map_concept("us-gaap:SomethingWeDoNotTrack") is None


def test_map_concept_returns_statement_and_priority():
    key, stmt, prio = map_concept("us-gaap:Assets")
    assert key == "total_assets" and stmt == "balance_sheet"
    # priority ordering: the specific revenue concept outranks the generic one
    assert (map_concept("RevenueFromContractWithCustomerExcludingAssessedTax")[2]
            < map_concept("Revenues")[2])


# ── period parsing ──────────────────────────────────────────────────────────

def test_parse_period():
    assert parse_period("duration_2024-09-29_2025-09-27") == ("duration", "2024-09-29", "2025-09-27")
    assert parse_period("instant_2025-09-27") == ("instant", None, "2025-09-27")
    assert parse_period("garbage") is None


# ── extractor ─────────────────────────────────────────────────────────────────

def _filing(form="10-K"):
    return FilingRef(filing_id="F1", cik="0000320193", ticker="AAPL", form_type=form,
                     filing_date="2025-11-01", period_of_report="2025-09-27",
                     fiscal_year=2025, fiscal_period="FY")


def _income_frame():
    return pd.DataFrame([
        # consolidated total revenue (annual) — kept
        {"concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
         "numeric_value": 416161e6, "period_key": "duration_2024-09-29_2025-09-27",
         "is_dimensioned": False, "fiscal_period": "FY"},
        # a generic Revenues for the SAME period — lower priority, must NOT override
        {"concept": "us-gaap:Revenues", "numeric_value": 999e6,
         "period_key": "duration_2024-09-29_2025-09-27", "is_dimensioned": False,
         "fiscal_period": "FY"},
        # dimensioned (segment) revenue — must be ignored
        {"concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
         "numeric_value": 307003e6, "period_key": "duration_2024-09-29_2025-09-27",
         "is_dimensioned": True, "fiscal_period": "FY"},
        # a quarterly duration — must be dropped for a 10-K
        {"concept": "us-gaap:Revenues", "numeric_value": 100e6,
         "period_key": "duration_2025-06-29_2025-09-27", "is_dimensioned": False,
         "fiscal_period": "Q4"},
        # unknown concept — ignored
        {"concept": "us-gaap:SomethingElse", "numeric_value": 5e6,
         "period_key": "duration_2024-09-29_2025-09-27", "is_dimensioned": False},
        # prior-year comparative (annual) — kept as its own period
        {"concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
         "numeric_value": 391035e6, "period_key": "duration_2023-10-01_2024-09-28",
         "is_dimensioned": False, "fiscal_period": "FY"},
    ])


def _balance_frame():
    return pd.DataFrame([
        {"concept": "us-gaap:Assets", "numeric_value": 364980e6,
         "period_key": "instant_2025-09-27", "is_dimensioned": False},
    ])


def test_extractor_filters_dimensions_and_picks_priority_and_period():
    facts = facts_from_frames({"inc": _income_frame(), "bs": _balance_frame()}, _filing("10-K"))
    by = {(f.canonical_key, f.period_end): f for f in facts}

    rev25 = by[("revenue", "2025-09-27")]
    assert rev25.value == pytest.approx(416161e6)        # specific concept wins, not 999e6
    assert rev25.source_concept.endswith("ExcludingAssessedTax")
    assert rev25.fiscal_year == 2025 and rev25.unit == "USD"

    assert ("revenue", "2024-09-28") in by                # comparative kept
    assert all(f.period_end != "2025-09-27" or f.canonical_key != "revenue"
               or f.value != 307003e6 for f in facts)     # segment never leaked
    # quarterly duration dropped for a 10-K
    assert ("revenue", "2025-09-27") in by and len([f for f in facts if f.period_end == "2025-09-27" and f.canonical_key == "revenue"]) == 1

    bs = by[("total_assets", "2025-09-27")]
    assert bs.period_type == "instant" and bs.period_start is None


def test_extractor_10q_keeps_quarterly_drops_annual():
    facts = facts_from_frames({"inc": _income_frame()}, _filing("10-Q"))
    periods = {(f.canonical_key, f.period_end) for f in facts}
    # the ~90-day Q4 period is kept; the annual ones are dropped
    assert ("revenue", "2025-09-27") in periods
    rev = next(f for f in facts if f.canonical_key == "revenue")
    assert rev.value == pytest.approx(100e6) and rev.fiscal_period == "Q4"


# ── validator ─────────────────────────────────────────────────────────────────

def test_validate_period_identities():
    ok = {"revenue": 100.0, "cost_of_revenue": 60.0, "gross_profit": 40.0,
          "total_assets": 200.0, "total_liabilities": 120.0, "total_equity": 80.0}
    assert validate_period(ok) == []

    bad = {"revenue": 100.0, "cost_of_revenue": 60.0, "gross_profit": 10.0}  # 40 != 10
    issues = validate_period(bad)
    assert any(i.rule == "gross_profit" for i in issues)


def test_flag_low_confidence_marks_bad_period_only():
    good = FinancialFact("c", "T", "revenue", "income_statement", 100.0, "USD",
                         "duration", "2025-12-31", "2025-01-01", 2025, "FY", "x", "xbrl", "F")
    cogs = FinancialFact("c", "T", "cost_of_revenue", "income_statement", 60.0, "USD",
                         "duration", "2025-12-31", "2025-01-01", 2025, "FY", "x", "xbrl", "F")
    gp = FinancialFact("c", "T", "gross_profit", "income_statement", 5.0, "USD",
                       "duration", "2025-12-31", "2025-01-01", 2025, "FY", "x", "xbrl", "F")
    out = {f.canonical_key: f for f in flag_low_confidence([good, cogs, gp])}
    assert out["gross_profit"].confidence == 0.5  # 100-60=40 != 5 → flagged


# ── store ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store.settings, "facts_db_path", str(tmp_path / "facts.db"))
    yield


def _fact(key, value, period_end, ticker="AAPL"):
    return FinancialFact("0000320193", ticker, key, "income_statement", value, "USD",
                         "duration", period_end, "2024-01-01", 2025, "FY",
                         "us-gaap:X", "xbrl", "F1")


def test_store_roundtrip_and_filters(temp_db):
    store.upsert_facts([
        _fact("revenue", 416161e6, "2025-09-27"),
        _fact("revenue", 391035e6, "2024-09-28"),
        _fact("net_income", 99803e6, "2025-09-27"),
    ], filing_date="2025-11-01")

    res = store.get_financials("aapl", metrics=["revenue"], periods=1)
    assert res["ticker"] == "AAPL"
    assert list(res["metrics"]) == ["revenue"]
    assert len(res["metrics"]["revenue"]) == 1                  # periods cap
    assert res["metrics"]["revenue"][0]["period_end"] == "2025-09-27"  # newest first
    assert res["metrics"]["revenue"][0]["value"] == pytest.approx(416161e6)


def test_store_newest_filing_wins_on_conflict(temp_db):
    store.upsert_facts([_fact("revenue", 416161e6, "2025-09-27")], filing_date="2025-11-01")
    # an OLDER filing reports the same period with a stale number → must NOT overwrite
    store.upsert_facts([_fact("revenue", 400000e6, "2025-09-27")], filing_date="2024-11-01")
    res = store.get_financials("AAPL", metrics=["revenue"])
    assert res["metrics"]["revenue"][0]["value"] == pytest.approx(416161e6)
    # a NEWER filing (restatement) supersedes
    store.upsert_facts([_fact("revenue", 416000e6, "2025-09-27")], filing_date="2026-02-01")
    res = store.get_financials("AAPL", metrics=["revenue"])
    assert res["metrics"]["revenue"][0]["value"] == pytest.approx(416000e6)


def test_get_financials_empty_for_unknown_ticker(temp_db):
    assert store.get_financials("ZZZZ")["metrics"] == {}
