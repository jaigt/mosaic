"""Form 4 insider-trade tracker — per-ticker insider buy/sell activity.

Insider open-market buying is a classic value signal. We fetch a company's
recent Form 4 filings from EDGAR, normalize their transaction rows, and
aggregate into an :class:`InsiderActivity`. The aggregation
(``summarize_insider_transactions``) is PURE and unit-tested; the EDGAR fetch is
isolated in ``get_insider_activity`` with an injectable company resolver.

Needs no API key/quota — EDGAR only.
"""
import logging
import math
from typing import Callable, Optional

from backend.holdings.models import InsiderActivity, InsiderTxn

logger = logging.getLogger(__name__)

# SEC Form 4 transaction codes we treat as open-market buy / sell. Other codes
# (A=grant, G=gift, M=option exercise, F=tax withholding, etc.) are "other".
_BUY_CODES = {"P"}
_SELL_CODES = {"S"}

# Defaults: how many recent Form 4 filings to pull and the max transactions to
# return. Each filing is an EDGAR fetch, so keep the filing count modest.
_DEFAULT_FILINGS = 12
_DEFAULT_MAX_TXNS = 40


def _classify(code: str) -> str:
    code = (code or "").upper().strip()
    if code in _BUY_CODES:
        return "buy"
    if code in _SELL_CODES:
        return "sell"
    return "other"


def _num(v) -> Optional[float]:
    """Coerce a possibly-NaN/None/str numeric to float or None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def summarize_insider_transactions(ticker: str, rows: list) -> InsiderActivity:
    """Aggregate normalized transaction rows into InsiderActivity. PURE.

    Each row is a dict with keys: insider, position, date, code, description,
    shares, price, value.
    """
    txns: list[InsiderTxn] = []
    buys = sells = 0
    bought = sold = 0.0
    for r in rows:
        code = (r.get("code") or "").upper().strip()
        kind = _classify(code)
        shares = _num(r.get("shares")) or 0.0
        txns.append(InsiderTxn(
            insider=str(r.get("insider") or "Unknown"),
            position=str(r.get("position") or ""),
            date=str(r.get("date") or ""),
            txn_type=kind,
            code=code,
            description=str(r.get("description") or ""),
            shares=shares,
            price=_num(r.get("price")),
            value=_num(r.get("value")),
        ))
        if kind == "buy":
            buys += 1
            bought += shares
        elif kind == "sell":
            sells += 1
            sold += shares
    return InsiderActivity(
        ticker=ticker.upper(), transactions=txns,
        buys=buys, sells=sells, bought_shares=bought, sold_shares=sold,
    )


def _rows_from_form4(obj) -> list:
    """Normalize one Form4 object's ``to_dataframe()`` into row dicts."""
    df = obj.to_dataframe()
    out = []
    if df is None or len(df) == 0:
        return out
    for rec in df.to_dict(orient="records"):
        out.append({
            "insider": rec.get("Insider"),
            "position": rec.get("Position"),
            "date": str(rec.get("Date"))[:10],  # YYYY-MM-DD (drop any time part)
            "code": rec.get("Code"),
            "description": rec.get("Description"),
            "shares": rec.get("Shares"),
            "price": rec.get("Price"),
            "value": rec.get("Value"),
        })
    return out


def get_insider_activity(
    ticker: str,
    limit_filings: int = _DEFAULT_FILINGS,
    max_transactions: int = _DEFAULT_MAX_TXNS,
    company_fn: Optional[Callable] = None,
) -> InsiderActivity:
    """Fetch and aggregate recent Form 4 insider activity for ``ticker``.

    ``company_fn(ticker) -> Company`` is injectable for testing. A per-filing
    failure is skipped rather than failing the whole call.
    """
    if company_fn is None:
        from edgar import Company  # noqa: PLC0415
        company_fn = Company

    rows: list = []
    try:
        filings = company_fn(ticker).get_filings(form="4")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Insider fetch failed for {ticker}: {e}")
        return InsiderActivity(ticker=ticker.upper())

    for filing in list(filings)[:limit_filings]:
        try:
            rows.extend(_rows_from_form4(filing.obj()))
        except Exception as e:  # noqa: BLE001 — skip a bad filing
            logger.debug(f"Skipping a Form 4 for {ticker}: {e}")
        if len(rows) >= max_transactions:
            break

    return summarize_insider_transactions(ticker, rows[:max_transactions])
