"""Tests for the watchlist store + the pure dashboard row/diff logic. No network,
no model (build_row takes already-fetched inputs)."""
import pytest

from backend.watchlist import store as wl_store
from backend.watchlist.dashboard import build_row, _diff


def _fin(data: dict[str, dict[str, float]], ticker="TEST") -> dict:
    metrics = {}
    for key, by_pe in data.items():
        metrics[key] = [{"period_end": pe, "fiscal_year": int(pe[:4]), "fiscal_period": "FY",
                         "value": v, "unit": "USD", "source_concept": "x",
                         "source_method": "xbrl", "filing_id": "F", "confidence": 1.0}
                        for pe, v in sorted(by_pe.items(), reverse=True)]
    return {"ticker": ticker, "metrics": metrics}


CORE = _fin({
    "revenue": {"2024-12-31": 350.0, "2025-12-31": 400.0},
    "cost_of_revenue": {"2025-12-31": 240.0},
    "operating_income": {"2025-12-31": 120.0},
    "net_income": {"2025-12-31": 100.0},
    "depreciation_amortization": {"2025-12-31": 20.0},
    "operating_cash_flow": {"2025-12-31": 130.0},
    "capex": {"2025-12-31": 30.0},
    "total_equity": {"2025-12-31": 200.0},
    "total_assets": {"2025-12-31": 500.0},
    "long_term_debt": {"2025-12-31": 80.0},
    "cash_and_equivalents": {"2025-12-31": 50.0},
    "shares_outstanding": {"2025-12-31": 50.0},
    "income_tax": {"2025-12-31": 25.0},
    "pretax_income": {"2025-12-31": 125.0},
})


# ── store ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_wl(tmp_path, monkeypatch):
    monkeypatch.setattr(wl_store.settings, "watchlist_db_path", str(tmp_path / "wl.db"))
    yield


def test_add_list_remove_idempotent(temp_wl):
    assert wl_store.add_ticker("aapl") is True
    wl_store.add_ticker("AAPL")           # idempotent
    wl_store.add_ticker("msft")
    assert wl_store.list_tickers() == ["AAPL", "MSFT"]
    assert wl_store.add_ticker("  ") is False
    wl_store.remove_ticker("AAPL")
    assert wl_store.list_tickers() == ["MSFT"]


def test_snapshot_roundtrip(temp_wl):
    assert wl_store.get_snapshot("AAPL") is None
    wl_store.save_snapshot("AAPL", {"pe": 30.0})
    assert wl_store.get_snapshot("AAPL")["pe"] == 30.0


# ── build_row (pure) ──────────────────────────────────────────────────────────

def test_build_row_covered_has_flags_and_metrics():
    row, snap = build_row("TEST", CORE,
                          price_snapshot={"price": 20.0, "shares_outstanding": 50.0})
    assert row["covered"] is True
    assert row["key_metrics"]["net_margin"] == pytest.approx(0.25)
    assert any(f["type"] == "valuation" for f in row["flags"])
    assert any(f["type"] == "fundamental" for f in row["flags"])
    assert snap["covered"] is True and snap["pe"] is not None


def test_build_row_uncovered_filer():
    fin = _fin({"total_assets": {"2025-12-31": 100.0}})  # no revenue → bank-like
    row, snap = build_row("JPM", fin)
    assert row["covered"] is False
    assert row["flags"][0]["type"] == "coverage"
    assert snap == {"covered": False}


def test_build_row_new_filing_flag():
    row, _ = build_row("TEST", CORE, price_snapshot={"price": 20.0},
                       ingested_filing_date="2024-11-01",
                       edgar_latest_filing_date="2025-11-01")
    assert row["new_filing"]["available"] is True
    assert any(f["type"] == "filing" for f in row["flags"])


def test_diff_surfaces_material_changes():
    prev = {"pe": 30.0, "signal_labels": ["High net margin"], "ingested_filing_date": "2024-11-01"}
    cur = {"pe": 40.0, "signal_labels": ["High net margin", "Low leverage"],
           "ingested_filing_date": "2025-11-01"}
    changes = _diff(prev, cur)
    assert any("P/E" in c for c in changes)
    assert any("New signal: Low leverage" in c for c in changes)
    assert any("New filing ingested" in c for c in changes)


def test_diff_quiet_when_unchanged():
    snap = {"pe": 30.0, "fcf_yield": 0.05, "signal_labels": ["X"]}
    assert _diff(snap, dict(snap)) == []
