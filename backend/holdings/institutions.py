"""13F institutional-holdings tracker — a fund's reported portfolio.

Scope note: 13F is filed BY an institution and lists THAT fund's holdings, so
this answers "what does <fund> hold?" (well-supported). The reverse — "which
funds hold <ticker>?" — requires aggregating across all funds' 13Fs (a holdings
index EDGAR doesn't expose directly) and is intentionally out of scope here.

``summarize_13f`` is PURE and unit-tested; the EDGAR fetch is isolated in
``get_fund_holdings`` with an injectable company resolver. EDGAR only — no key.
"""
import logging
import math
from typing import Callable, Optional

from backend.holdings.models import FundHoldings, Holding

logger = logging.getLogger(__name__)

_DEFAULT_TOP = 25


def _num(v) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def summarize_13f(
    fund: str,
    report_period: str,
    total_value: float,
    records: list,
    top: int = _DEFAULT_TOP,
) -> FundHoldings:
    """Aggregate 13F infotable records into a FundHoldings (top-N by value). PURE.

    ``records`` are dicts with keys: issuer, ticker, cusip, value, shares.
    Positions in the same issuer/cusip are merged (a fund can list a holding
    across multiple rows/managers).
    """
    merged: dict = {}
    for r in records:
        key = (r.get("cusip") or r.get("issuer") or r.get("ticker") or "?")
        h = merged.get(key)
        value = _num(r.get("value"))
        shares = _num(r.get("shares"))
        if h is None:
            merged[key] = Holding(
                issuer=str(r.get("issuer") or ""),
                ticker=(str(r.get("ticker")) if r.get("ticker") else None),
                cusip=str(r.get("cusip") or ""),
                value=value, shares=shares, pct=0.0,
            )
        else:
            h.value += value
            h.shares += shares

    holdings = sorted(merged.values(), key=lambda h: h.value, reverse=True)
    tv = total_value or sum(h.value for h in holdings)
    if tv:
        for h in holdings:
            h.pct = round(h.value / tv * 100.0, 2)

    return FundHoldings(
        fund=fund, report_period=str(report_period or ""),
        total_value=tv, total_holdings=len(merged), holdings=holdings[:top],
    )


def _records_from_infotable(tf) -> list:
    """Normalize a ThirteenF.infotable DataFrame into row dicts."""
    it = getattr(tf, "infotable", None)
    if it is None or len(it) == 0:
        return []
    out = []
    for rec in it.to_dict(orient="records"):
        out.append({
            "issuer": rec.get("Issuer"),
            "ticker": rec.get("Ticker"),
            "cusip": rec.get("Cusip"),
            "value": rec.get("Value"),
            "shares": rec.get("SharesPrnAmount"),
        })
    return out


def get_fund_holdings(
    fund: str,
    top: int = _DEFAULT_TOP,
    company_fn: Optional[Callable] = None,
) -> FundHoldings:
    """Fetch the latest 13F-HR for ``fund`` (a ticker/CIK EDGAR can resolve) and
    summarize its top holdings. ``company_fn`` injectable for testing."""
    if company_fn is None:
        from edgar import Company  # noqa: PLC0415
        company_fn = Company

    try:
        filings = company_fn(fund).get_filings(form="13F-HR")
        first = list(filings)[0] if filings else None
        if first is None:
            return FundHoldings(fund=fund, report_period="", total_value=0.0, total_holdings=0)
        tf = first.obj()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"13F fetch failed for {fund}: {e}")
        return FundHoldings(fund=fund, report_period="", total_value=0.0, total_holdings=0)

    name = (
        getattr(tf, "management_company_name", None)
        or getattr(tf, "investment_manager", None)
        or fund
    )
    return summarize_13f(
        fund=str(name),
        report_period=getattr(tf, "report_period", "") or "",
        total_value=_num(getattr(tf, "total_value", 0.0)),
        records=_records_from_infotable(tf),
        top=top,
    )
