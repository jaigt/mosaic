"""On-demand watchlist dashboard.

For each saved ticker, runs the (deterministic) valuation engine + signals over
the fact base, adds a live price, best-effort filing/insider/smart-money context,
and diffs against the last view to surface "what changed". No scheduler — it's
computed when the dashboard is opened, and a fresh snapshot is saved each time.

``build_row`` is PURE (takes already-fetched inputs) so it's unit-testable;
``build_dashboard`` does the (parallel, best-effort) fetching.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from backend.valuation import (
    compute_metrics,
    compute_valuation,
    derive_signals,
)

logger = logging.getLogger(__name__)


def _verdict(upside: Optional[float]) -> Optional[str]:
    if upside is None:
        return None
    if upside >= 0.20:
        return "cheap"
    if upside <= -0.20:
        return "expensive"
    return "fair"


def _move(prev: Optional[float], cur: Optional[float], label: str, fmt: Callable[[float], str],
          rel_tol: float = 0.05) -> Optional[str]:
    """A human change string if a value moved materially since last view."""
    if prev is None or cur is None:
        return None
    scale = max(abs(prev), abs(cur), 1e-9)
    if abs(cur - prev) / scale < rel_tol:
        return None
    return f"{label} {fmt(prev)}→{fmt(cur)}"


def build_row(
    ticker: str,
    fin: dict,
    *,
    price_snapshot: Optional[dict] = None,
    prev_snapshot: Optional[dict] = None,
    insider_summary: Optional[str] = None,
    smart_money_summary: Optional[str] = None,
    ingested_filing_date: Optional[str] = None,
    edgar_latest_filing_date: Optional[str] = None,
) -> tuple[dict, dict]:
    """Build one dashboard row + the snapshot to persist. PURE."""
    ticker = ticker.upper()
    covered = "revenue" in (fin.get("metrics") or {})
    if not covered:
        row = {"ticker": ticker, "covered": False, "flags": [
            {"type": "coverage", "direction": "info",
             "label": "Limited structured coverage (bank/insurer or non-standard filer)"}],
            "key_metrics": {}, "valuation": {}, "changed": [], "new_filing": None,
            "holdings": {}}
        return row, {"covered": False}

    metrics = compute_metrics(fin)
    price = (price_snapshot or {}).get("price")
    shares = (price_snapshot or {}).get("shares_outstanding")
    val = compute_valuation(fin, price=price, shares_outstanding=shares)
    signals = derive_signals(metrics, val)

    lp = metrics["latest_period"]
    pm = metrics["per_period"].get(lp, {})
    dcf = val.get("dcf") or {}
    mult = val.get("multiples") or {}
    upside = dcf.get("upside_vs_price")
    verdict = _verdict(upside)

    rev_rows = fin.get("metrics", {}).get("revenue", [])
    key_metrics = {
        "revenue": rev_rows[0]["value"] if rev_rows else None,
        "net_margin": pm.get("net_margin"),
        "fcf_margin": pm.get("fcf_margin"),
        "revenue_growth_yoy": metrics["trends"].get("revenue_growth_yoy"),
        "net_debt_to_ebitda": pm.get("net_debt_to_ebitda"),
        "roic_approx": pm.get("roic_approx"),
    }

    flags: list[dict] = []
    if verdict:
        d = {"cheap": "bull", "expensive": "bear", "fair": "neutral"}[verdict]
        extra = f" (~{abs(upside) * 100:.0f}% {'below' if upside > 0 else 'above'} DCF)" if upside is not None else ""
        flags.append({"type": "valuation", "direction": d, "label": f"{verdict.title()} vs DCF{extra}"})
    for s in signals:
        if s.dimension == "valuation":
            continue  # already covered by the verdict flag
        flags.append({"type": "fundamental", "direction": s.direction, "label": f"{s.label} ({s.detail})"})

    new_filing = None
    if edgar_latest_filing_date and ingested_filing_date and edgar_latest_filing_date > ingested_filing_date:
        new_filing = {"available": True, "edgar_date": edgar_latest_filing_date,
                      "ingested_date": ingested_filing_date}
        flags.append({"type": "filing", "direction": "info",
                      "label": f"New filing on EDGAR ({edgar_latest_filing_date}) — not yet ingested"})

    holdings = {}
    if insider_summary:
        holdings["insider"] = insider_summary.strip().split("\n")[0][:140]
    if smart_money_summary:
        holdings["smart_money"] = smart_money_summary.strip().split("\n")[0][:140]

    # Snapshot of the comparable figures for next-view diffing.
    snap = {
        "covered": True, "pe": mult.get("pe"), "fcf_yield": mult.get("fcf_yield"),
        "dcf_upside": upside, "net_margin": pm.get("net_margin"),
        "revenue_growth_yoy": key_metrics["revenue_growth_yoy"],
        "net_debt_to_ebitda": pm.get("net_debt_to_ebitda"),
        "signal_labels": sorted(s.label for s in signals),
        "ingested_filing_date": ingested_filing_date,
    }

    changed = _diff(prev_snapshot, snap) if prev_snapshot else []

    row = {
        "ticker": ticker, "covered": True, "price": price, "verdict": verdict,
        "valuation": {"dcf_intrinsic": dcf.get("intrinsic_value_per_share"),
                      "dcf_low": dcf.get("range_low"), "dcf_high": dcf.get("range_high"),
                      "pe": mult.get("pe"), "fcf_yield": mult.get("fcf_yield"),
                      "upside_vs_price": upside},
        "key_metrics": key_metrics, "flags": flags, "changed": changed,
        "new_filing": new_filing, "holdings": holdings,
    }
    return row, snap


def _diff(prev: dict, cur: dict) -> list[str]:
    """Human-readable changes since the last snapshot. PURE."""
    out: list[str] = []
    for m in (
        _move(prev.get("pe"), cur.get("pe"), "P/E", lambda v: f"{v:.1f}x"),
        _move(prev.get("dcf_upside"), cur.get("dcf_upside"), "DCF gap", lambda v: f"{v * 100:.0f}%", rel_tol=0.10),
        _move(prev.get("net_margin"), cur.get("net_margin"), "Net margin", lambda v: f"{v * 100:.1f}%"),
        _move(prev.get("revenue_growth_yoy"), cur.get("revenue_growth_yoy"), "Rev growth", lambda v: f"{v * 100:.1f}%"),
        _move(prev.get("net_debt_to_ebitda"), cur.get("net_debt_to_ebitda"), "Leverage", lambda v: f"{v:.1f}x"),
    ):
        if m:
            out.append(m)
    prev_sig = set(prev.get("signal_labels") or [])
    cur_sig = set(cur.get("signal_labels") or [])
    for s in sorted(cur_sig - prev_sig):
        out.append(f"New signal: {s}")
    for s in sorted(prev_sig - cur_sig):
        out.append(f"Cleared: {s}")
    if (cur.get("ingested_filing_date") and prev.get("ingested_filing_date")
            and cur["ingested_filing_date"] > prev["ingested_filing_date"]):
        out.append(f"New filing ingested ({cur['ingested_filing_date']})")
    return out


# ── Orchestration (best-effort, parallel fetching) ────────────────────────────

def build_dashboard(
    tickers: Optional[list[str]] = None,
    *,
    save: bool = True,
) -> list[dict]:
    """Build dashboard rows for the watchlist (or a given list). Fetches price /
    insider / smart-money / EDGAR-latest per ticker in parallel, best-effort;
    saves a fresh snapshot per ticker (so next view can diff)."""
    from backend.watchlist import store as wl_store

    tickers = tickers if tickers is not None else wl_store.list_tickers()
    if not tickers:
        return []

    def _one(ticker: str) -> dict:
        from backend.facts.store import get_financials, latest_filing_date
        from backend.valuation import get_price_snapshot

        fin = get_financials(ticker)
        price_snapshot = _best_effort(lambda: get_price_snapshot(ticker))
        insider = _best_effort(lambda: _insider_summary(ticker))
        smart = _best_effort(lambda: _smart_money_summary(ticker))
        edgar_latest = _best_effort(lambda: _edgar_latest_filing_date(ticker))
        ingested = _best_effort(lambda: latest_filing_date(ticker))
        prev = wl_store.get_snapshot(ticker)
        row, snap = build_row(
            ticker, fin, price_snapshot=price_snapshot, prev_snapshot=prev,
            insider_summary=insider, smart_money_summary=smart,
            ingested_filing_date=ingested, edgar_latest_filing_date=edgar_latest,
        )
        if save:
            wl_store.save_snapshot(ticker, snap)
        return row

    with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
        return list(pool.map(_one, tickers))


def _best_effort(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — enrichments are optional
        logger.info("watchlist enrichment skipped: %s", e)
        return None


def _ensure_edgar_identity() -> None:
    """edgartools needs an identity set before any EDGAR call. The fetcher sets
    it at import, but the holdings path may run before that import — set it here
    so the watchlist's insider enrichment is robust to import order."""
    import edgar
    from backend.config import settings
    edgar.set_identity(settings.sec_user_agent)


def _insider_summary(ticker: str) -> Optional[str]:
    _ensure_edgar_identity()
    from backend.holdings import get_insider_activity
    return get_insider_activity(ticker).summary_text()


def _smart_money_summary(ticker: str) -> Optional[str]:
    from backend.holdings import funds_holding
    return funds_holding(ticker).summary_text()


def _edgar_latest_filing_date(ticker: str) -> Optional[str]:
    """Best-effort: the date of the most recent 10-K/10-Q on EDGAR (to flag a
    filing newer than what we've ingested)."""
    _ensure_edgar_identity()
    from backend.ingestion.edgar_fetcher import resolve_filing
    _, meta = resolve_filing(ticker, "10-K", None)
    return str(meta.get("filing_date") or "") or None
