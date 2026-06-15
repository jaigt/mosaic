"""Tests for the holdings trackers: pure aggregation (insider + 13F) and the
EDGAR-fetch wrappers with an injected fake Company (no network)."""
import math

import pandas as pd
import pytest

from backend.holdings.insiders import get_insider_activity, summarize_insider_transactions
from backend.holdings.institutions import get_fund_holdings, summarize_13f


# ── insider aggregation (pure) ────────────────────────────────────────────────

def test_summarize_classifies_buys_sells_and_net():
    rows = [
        {"insider": "A", "position": "CEO", "date": "2026-05-01", "code": "P",
         "description": "Open Market Purchase", "shares": 1000, "price": 10.0, "value": 10000},
        {"insider": "B", "position": "Dir", "date": "2026-05-02", "code": "S",
         "description": "Open Market Sale", "shares": 400, "price": 12.0, "value": 4800},
        {"insider": "C", "position": "CFO", "date": "2026-05-03", "code": "G",
         "description": "Gift", "shares": 50, "price": None, "value": None},
    ]
    act = summarize_insider_transactions("aapl", rows)
    assert act.ticker == "AAPL"
    assert act.buys == 1 and act.sells == 1
    assert act.bought_shares == 1000 and act.sold_shares == 400
    assert act.net_shares == 600
    assert [t.txn_type for t in act.transactions] == ["buy", "sell", "other"]
    assert act.transactions[2].price is None


def test_summarize_handles_nan_and_missing():
    rows = [{"code": "P", "shares": float("nan"), "price": float("nan"), "value": None}]
    act = summarize_insider_transactions("X", rows)
    assert act.transactions[0].shares == 0.0
    assert act.transactions[0].price is None
    assert act.bought_shares == 0.0


def test_insider_summary_text_empty():
    act = summarize_insider_transactions("NVDA", [])
    assert "No recent insider" in act.summary_text()


# ── insider fetch (fake Company) ──────────────────────────────────────────────

class _FakeForm4:
    def __init__(self, df):
        self._df = df

    def to_dataframe(self):
        return self._df


class _FakeFiling:
    def __init__(self, obj):
        self._obj = obj

    def obj(self):
        return self._obj


class _FakeFilings(list):
    def get_filings(self, form):  # not used; kept for parity
        return self


class _FakeCompany:
    def __init__(self, filings):
        self._filings = filings

    def get_filings(self, form):
        assert form == "4"
        return self._filings


def test_get_insider_activity_with_fake_company():
    df = pd.DataFrame([
        {"Insider": "Tim", "Position": "CEO", "Date": "2026-05-01", "Code": "P",
         "Description": "Open Market Purchase", "Shares": 500, "Price": 190.0, "Value": 95000},
        {"Insider": "Tim", "Position": "CEO", "Date": "2026-05-01", "Code": "S",
         "Description": "Open Market Sale", "Shares": 200, "Price": 191.0, "Value": 38200},
    ])
    filings = [_FakeFiling(_FakeForm4(df))]
    act = get_insider_activity("AAPL", company_fn=lambda t: _FakeCompany(filings))
    assert act.buys == 1 and act.sells == 1
    assert act.bought_shares == 500 and act.sold_shares == 200


def test_get_insider_activity_skips_bad_filing():
    class Boom:
        def obj(self):
            raise RuntimeError("bad xml")

    act = get_insider_activity("AAPL", company_fn=lambda t: _FakeCompany([Boom()]))
    assert act.transactions == []   # skipped, no crash


def test_get_insider_activity_fetch_failure_returns_empty():
    def boom(t):
        raise RuntimeError("edgar down")

    act = get_insider_activity("AAPL", company_fn=boom)
    assert act.ticker == "AAPL" and act.transactions == []


# ── 13F aggregation (pure) ────────────────────────────────────────────────────

def test_summarize_13f_merges_and_ranks():
    records = [
        {"issuer": "ALLY FINL", "ticker": "ALLY", "cusip": "C1", "value": 100, "shares": 10},
        {"issuer": "ALLY FINL", "ticker": "ALLY", "cusip": "C1", "value": 50, "shares": 5},   # merge
        {"issuer": "APPLE INC", "ticker": "AAPL", "cusip": "C2", "value": 600, "shares": 3},
    ]
    fh = summarize_13f("Berkshire", "2026-03-31", total_value=750, records=records, top=10)
    assert fh.total_holdings == 2          # merged ALLY rows
    assert fh.holdings[0].ticker == "AAPL"  # ranked by value desc
    assert fh.holdings[0].pct == pytest.approx(80.0)
    ally = fh.holdings[1]
    assert ally.value == 150 and ally.shares == 15
    assert ally.pct == pytest.approx(20.0)


def test_summarize_13f_infers_total_when_missing():
    records = [{"issuer": "X", "ticker": "X", "cusip": "C", "value": 200, "shares": 1}]
    fh = summarize_13f("F", "2026-03-31", total_value=0, records=records)
    assert fh.total_value == 200 and fh.holdings[0].pct == pytest.approx(100.0)


def test_summarize_13f_top_n():
    records = [{"issuer": f"I{i}", "ticker": f"T{i}", "cusip": f"C{i}", "value": i, "shares": 1}
               for i in range(1, 11)]
    fh = summarize_13f("F", "p", total_value=55, records=records, top=3)
    assert len(fh.holdings) == 3
    assert [h.ticker for h in fh.holdings] == ["T10", "T9", "T8"]


# ── 13F fetch (fake) ──────────────────────────────────────────────────────────

class _FakeThirteenF:
    def __init__(self, infotable, **attrs):
        self.infotable = infotable
        self.management_company_name = attrs.get("name", "Test Fund")
        self.report_period = attrs.get("period", "2026-03-31")
        self.total_value = attrs.get("total_value", 0)


def test_get_fund_holdings_with_fake_company():
    it = pd.DataFrame([
        {"Issuer": "APPLE INC", "Ticker": "AAPL", "Cusip": "C2", "Value": 600, "SharesPrnAmount": 3},
        {"Issuer": "ALLY", "Ticker": "ALLY", "Cusip": "C1", "Value": 400, "SharesPrnAmount": 8},
    ])
    tf = _FakeThirteenF(it, name="Berkshire Hathaway", total_value=1000)
    company = type("C", (), {"get_filings": lambda self, form: [_FakeFiling(tf)]})()
    fh = get_fund_holdings("BRK-B", company_fn=lambda f: company)
    assert fh.fund == "Berkshire Hathaway"
    assert fh.total_holdings == 2
    assert fh.holdings[0].ticker == "AAPL" and fh.holdings[0].pct == pytest.approx(60.0)


def test_get_fund_holdings_no_filings():
    company = type("C", (), {"get_filings": lambda self, form: []})()
    fh = get_fund_holdings("XYZ", company_fn=lambda f: company)
    assert fh.total_holdings == 0 and fh.holdings == []
