"""Tests for the deterministic valuation engine. Pure — no network, no yfinance,
no model. Synthetic fundamentals exercise the metric + DCF math."""
import pytest

from backend.valuation.engine import (
    DCFAssumptions,
    compute_metrics,
    compute_valuation,
    metrics_for_period,
)


def _fin(data: dict[str, dict[str, float]], ticker="TEST") -> dict:
    """Build a get_financials()-shaped dict from {key: {period_end: value}}."""
    metrics: dict[str, list[dict]] = {}
    for key, by_pe in data.items():
        rows = [{"period_end": pe, "fiscal_year": int(pe[:4]), "fiscal_period": "FY",
                 "value": v, "unit": "USD", "source_concept": "x",
                 "source_method": "xbrl", "filing_id": "F", "confidence": 1.0}
                for pe, v in sorted(by_pe.items(), reverse=True)]
        metrics[key] = rows
    return {"ticker": ticker, "metrics": metrics}


# One rich latest year + two prior revenue points for growth.
SAMPLE = _fin({
    "revenue": {"2023-12-31": 300.0, "2024-12-31": 350.0, "2025-12-31": 400.0},
    "cost_of_revenue": {"2025-12-31": 240.0},
    "gross_profit": {"2025-12-31": 160.0},
    "operating_income": {"2025-12-31": 120.0},
    "net_income": {"2025-12-31": 100.0},
    "depreciation_amortization": {"2025-12-31": 20.0},
    "operating_cash_flow": {"2025-12-31": 130.0},
    "capex": {"2025-12-31": 30.0},
    "total_equity": {"2025-12-31": 200.0},
    "total_assets": {"2025-12-31": 500.0},
    "long_term_debt": {"2025-12-31": 80.0},
    "short_term_debt": {"2025-12-31": 20.0},
    "cash_and_equivalents": {"2025-12-31": 40.0},
    "short_term_investments": {"2025-12-31": 10.0},
    "current_assets": {"2025-12-31": 150.0},
    "current_liabilities": {"2025-12-31": 100.0},
    "interest_expense": {"2025-12-31": 10.0},
    "income_tax": {"2025-12-31": 25.0},
    "pretax_income": {"2025-12-31": 125.0},
    "shares_outstanding": {"2025-12-31": 50.0},
})


def test_per_period_metrics():
    m = compute_metrics(SAMPLE)
    p = m["per_period"]["2025-12-31"]
    assert p["gross_margin"] == pytest.approx(0.40)
    assert p["operating_margin"] == pytest.approx(0.30)
    assert p["net_margin"] == pytest.approx(0.25)
    assert p["fcf"] == pytest.approx(100.0)           # 130 OCF - 30 capex
    assert p["fcf_margin"] == pytest.approx(0.25)
    assert p["ebitda"] == pytest.approx(140.0)         # 120 OI + 20 D&A
    assert p["roe"] == pytest.approx(0.50)
    assert p["roa"] == pytest.approx(0.20)
    assert p["net_debt"] == pytest.approx(50.0)        # 100 debt - 50 cash
    assert p["net_debt_to_ebitda"] == pytest.approx(50 / 140)
    assert p["current_ratio"] == pytest.approx(1.5)
    assert p["interest_coverage"] == pytest.approx(12.0)
    assert p["effective_tax_rate"] == pytest.approx(0.20)
    assert p["roic_approx"] == pytest.approx(96 / 250)  # NOPAT 96 / IC 250


def test_trends():
    t = compute_metrics(SAMPLE)["trends"]
    assert t["revenue_growth_yoy"] == pytest.approx((400 - 350) / 350)
    assert t["revenue_cagr"] == pytest.approx((400 / 300) ** (1 / 2) - 1)


def test_gross_profit_derived_when_untagged():
    """A filer that doesn't tag gross_profit (e.g. GOOGL) still gets a gross
    margin from revenue - cost_of_revenue."""
    p = metrics_for_period({"revenue": 100.0, "cost_of_revenue": 55.0})  # no gross_profit
    assert p["gross_margin"] == pytest.approx(0.45)


def test_missing_inputs_yield_none_not_zero():
    p = metrics_for_period({"operating_income": 50.0})  # no revenue, no D&A inputs
    assert p["gross_margin"] is None
    assert p["net_debt"] is None
    assert p["ebitda"] == pytest.approx(50.0)  # OI present, D&A optional


def test_valuation_multiples_with_price():
    v = compute_valuation(SAMPLE, price=20.0)  # shares (50) come from the facts
    mult = v["multiples"]
    assert mult["market_cap"] == pytest.approx(1000.0)
    assert mult["enterprise_value"] == pytest.approx(1050.0)   # +50 net debt
    assert mult["pe"] == pytest.approx(10.0)
    assert mult["ev_ebitda"] == pytest.approx(7.5)
    assert mult["p_fcf"] == pytest.approx(10.0)
    assert mult["p_s"] == pytest.approx(2.5)
    assert mult["fcf_yield"] == pytest.approx(0.10)


def test_dcf_scaffold_is_sane_and_transparent():
    v = compute_valuation(SAMPLE, price=20.0)
    dcf = v["dcf"]
    assert dcf is not None
    assert dcf["range_low"] < dcf["intrinsic_value_per_share"] < dcf["range_high"]
    assert dcf["intrinsic_value_per_share"] > 0
    # assumptions are echoed back (transparency, not an oracle)
    assert set(dcf["assumptions"]) == {"years", "growth", "discount_rate", "terminal_growth"}
    assert dcf["upside_vs_price"] is not None


def test_valuation_without_price_still_does_dcf_no_multiples():
    v = compute_valuation(SAMPLE, price=None)
    assert v["multiples"] == {}
    assert v["dcf"] is not None                       # shares from facts → DCF works
    assert v["dcf"]["upside_vs_price"] is None        # no price to compare


def test_summary_formatters():
    from backend.valuation.summary import format_fundamentals, format_valuation
    fund = format_fundamentals(SAMPLE, compute_metrics(SAMPLE))
    assert "TEST" in fund and "Margins" in fund and "Growth" in fund
    assert "40.0%" in fund  # gross margin rendered as percent
    val = format_valuation(compute_valuation(SAMPLE, price=20.0))
    assert "P/E 10.0x" in val and "DCF intrinsic value" in val
    assert "not a recommendation" in val  # guardrail line present


def test_derive_signals_and_thesis_scaffold():
    from backend.valuation import derive_signals, format_thesis
    m = compute_metrics(SAMPLE)
    v = compute_valuation(SAMPLE, price=20.0)
    sigs = derive_signals(m, v)
    dirs = {(s.dimension, s.direction) for s in sigs}
    assert ("profitability", "bull") in dirs   # net margin 25%
    assert ("cash_flow", "bull") in dirs        # FCF margin 25%
    assert ("balance_sheet", "bull") in dirs    # net debt/EBITDA ~0.36x
    assert ("growth", "bull") in dirs           # revenue +14% YoY
    txt = format_thesis("TEST", m, v, sigs)
    assert "BULL:" in txt and "BEAR:" in txt and "VALUATION:" in txt
    assert "not investment advice" in txt


def test_custom_assumptions_override():
    v = compute_valuation(SAMPLE, price=20.0,
                          assumptions=DCFAssumptions(years=10, growth=0.05,
                                                     discount_rate=0.10, terminal_growth=0.02))
    a = v["dcf"]["assumptions"]
    assert a["years"] == 10 and a["growth"] == pytest.approx(0.05)
    assert a["discount_rate"] == pytest.approx(0.10)
