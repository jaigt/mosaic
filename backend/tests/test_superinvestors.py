"""Tests for the smart-money tracker: pure change/index logic, the cache
round-trip, refresh with an injected fake Company, and the registry."""
import pandas as pd
import pytest

from backend.holdings.superinvestors import (
    build_fund_rows,
    classify_change,
    funds_holding,
    funds_holding_from_rows,
    load_index,
    load_registry,
    refresh,
    save_index,
)


def test_classify_change():
    assert classify_change(100, 0) == "new"
    assert classify_change(0, 100) == "exited"
    assert classify_change(150, 100) == "added"
    assert classify_change(80, 100) == "trimmed"
    assert classify_change(100, 100) == "unchanged"


def test_build_fund_rows_tags_changes_and_exits():
    current = [
        {"issuer": "APPLE", "ticker": "AAPL", "cusip": "C1", "value": 600, "shares": 60},   # added
        {"issuer": "NVIDIA", "ticker": "NVDA", "cusip": "C2", "value": 400, "shares": 10},   # new
    ]
    prior = [
        {"issuer": "APPLE", "ticker": "AAPL", "cusip": "C1", "value": 500, "shares": 50},
        {"issuer": "KO", "ticker": "KO", "cusip": "C3", "value": 100, "shares": 5},          # exited
    ]
    rows = build_fund_rows("Buffett", "1067983", "2026-03-31", current, prior)
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["AAPL"]["change"] == "added" and by_ticker["AAPL"]["prev_shares"] == 50
    assert by_ticker["NVDA"]["change"] == "new"
    assert by_ticker["KO"]["change"] == "exited" and by_ticker["KO"]["shares"] == 0
    # pct of book is value / total current value (1000).
    assert by_ticker["AAPL"]["pct"] == pytest.approx(60.0)


def test_funds_holding_from_rows_filters_ranks_and_splits_exits():
    rows = [
        {"fund": "A", "cik": "1", "ticker": "AAPL", "issuer": "APPLE", "value": 100,
         "shares": 10, "pct": 5.0, "as_of": "p", "change": "added", "prev_shares": 8},
        {"fund": "B", "cik": "2", "ticker": "AAPL", "issuer": "APPLE", "value": 300,
         "shares": 30, "pct": 9.0, "as_of": "p", "change": "new", "prev_shares": 0},
        {"fund": "C", "cik": "3", "ticker": "AAPL", "issuer": "APPLE", "value": 0,
         "shares": 0, "pct": 0.0, "as_of": "p", "change": "exited", "prev_shares": 20},
        {"fund": "D", "cik": "4", "ticker": "MSFT", "issuer": "MSFT", "value": 999,
         "shares": 9, "pct": 1.0, "as_of": "p", "change": "added", "prev_shares": 1},
    ]
    own = funds_holding_from_rows("aapl", rows, refreshed_at="2026-06-15T00:00:00Z")
    assert own.ticker == "AAPL"
    assert [p.fund for p in own.positions] == ["B", "A"]   # by value desc, MSFT excluded
    assert [p.fund for p in own.exits] == ["C"]


def test_index_cache_round_trip(tmp_path):
    rows = [{"fund": "A", "cik": "1", "ticker": "AAPL", "issuer": "APPLE", "value": 100,
             "shares": 10, "pct": 5.0, "as_of": "p", "change": "added", "prev_shares": 8}]
    p = tmp_path / "idx.json"
    save_index(rows, p)
    idx = load_index(p)
    assert idx["funds"] == 1 and len(idx["rows"]) == 1
    own = funds_holding("AAPL", index_path=p)
    assert own.positions and own.positions[0].fund == "A"


def test_load_index_missing_is_empty(tmp_path):
    idx = load_index(tmp_path / "nope.json")
    assert idx["rows"] == []


def test_registry_loads():
    reg = load_registry()
    assert len(reg) >= 5
    assert all(f.get("cik") for f in reg)


# ── refresh with an injected fake Company ─────────────────────────────────────

class _FakeThirteenF:
    def __init__(self, infotable, period):
        self.infotable = infotable
        self.report_period = period
        self.management_company_name = "Fake Fund"


class _FakeFiling:
    def __init__(self, obj):
        self._obj = obj

    def obj(self):
        return self._obj


def test_refresh_builds_index_with_fake_company(tmp_path):
    cur = pd.DataFrame([{"Issuer": "APPLE", "Ticker": "AAPL", "Cusip": "C1", "Value": 600, "SharesPrnAmount": 60}])
    prior = pd.DataFrame([{"Issuer": "APPLE", "Ticker": "AAPL", "Cusip": "C1", "Value": 500, "SharesPrnAmount": 50}])
    filings = [_FakeFiling(_FakeThirteenF(cur, "2026-03-31")),
               _FakeFiling(_FakeThirteenF(prior, "2025-12-31"))]
    company = type("C", (), {"get_filings": lambda self, form: filings})()

    registry = [{"name": "TestFund", "cik": "999"}]
    p = tmp_path / "idx.json"
    result = refresh(registry=registry, company_fn=lambda cik: company, index_path=p)
    assert result["funds"] == 1 and result["rows"] == 1 and result["errors"] == []

    own = funds_holding("AAPL", index_path=p)
    assert own.positions[0].fund == "TestFund"
    assert own.positions[0].change == "added"   # 60 vs prior 50


def test_refresh_skips_bad_fund(tmp_path):
    def boom(cik):
        raise RuntimeError("edgar down")

    result = refresh(registry=[{"name": "Bad", "cik": "1"}], company_fn=boom,
                     index_path=tmp_path / "idx.json")
    assert result["funds"] == 0 and result["rows"] == 0
    assert result["errors"] and "Bad" in result["errors"][0]
