"""Market price snapshot via yfinance.

Isolated here (the only external market-data dependency) and fully best-effort:
returns ``None`` offline / on any error, so the rest of the valuation engine
keeps working on pure fundamentals. EDGAR has no prices, hence yfinance.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_price_snapshot(ticker: str) -> Optional[dict]:
    """Return ``{"price", "shares_outstanding", "currency"}`` or ``None``.

    Best-effort: any failure (offline, rate limit, API drift, unknown ticker)
    returns ``None`` rather than raising — price-based multiples simply won't be
    computed."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None
    try:
        import yfinance as yf  # imported lazily so the dep is optional at runtime

        fi = yf.Ticker(ticker).fast_info
        price = _first(fi, "last_price", "lastPrice")
        shares = _first(fi, "shares", "sharesOutstanding")
        currency = _first(fi, "currency") or "USD"
        if price is None:
            return None
        return {"price": float(price),
                "shares_outstanding": float(shares) if shares else None,
                "currency": currency}
    except Exception as e:  # noqa: BLE001 — price is optional
        logger.info("Price lookup for %s unavailable: %s", ticker, e)
        return None


def _first(obj, *keys):
    """Read the first present attribute/key (yfinance fast_info is dict-like)."""
    for k in keys:
        try:
            v = obj[k] if hasattr(obj, "__getitem__") else getattr(obj, k, None)
        except Exception:  # noqa: BLE001
            v = getattr(obj, k, None)
        if v is not None:
            return v
    return None
