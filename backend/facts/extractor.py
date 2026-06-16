"""Extract normalized :class:`FinancialFact` rows from a filing's XBRL.

The pure core, :func:`facts_from_frames`, takes already-fetched per-statement
DataFrames (so it's unit-testable with synthetic data, no network). The thin
:func:`extract_filing_facts` wrapper pulls those frames from an edgartools
``XBRL`` object via its ``FactQuery`` interface.

Key correctness rules learned from real filings:
- **`is_dimensioned == False`** only — dimensioned rows are segment/axis
  breakdowns (e.g. Products vs Services), not consolidated totals.
- **Duration length** classifies a period: a 10-K's statements carry ~365-day
  (annual) durations plus comparatives; a 10-Q carries ~90-day (quarterly) plus
  YTD. We keep the granularity matching the form and skip the rest, so we never
  double-count a 9-month YTD figure as a quarter.
- **Priority dedup:** when two concepts map to the same canonical key for the
  same period, the higher-priority concept (per the taxonomy order) wins.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from backend.facts.models import FinancialFact, FilingRef
from backend.facts.taxonomy import (
    PER_SHARE_KEYS,
    SHARE_COUNT_KEYS,
    map_concept,
)

logger = logging.getLogger(__name__)

STATEMENT_TYPES = ("IncomeStatement", "BalanceSheet", "CashFlowStatement")

# Duration-length thresholds (days) used to classify a duration period.
_ANNUAL_MIN_DAYS = 300
_QUARTER_MAX_DAYS = 120


def parse_period(period_key: str) -> tuple[str, Optional[str], str] | None:
    """Parse an edgartools ``period_key`` into ``(period_type, start, end)``.

    ``"duration_2024-09-29_2025-09-27"`` -> ``("duration", "2024-09-29", "2025-09-27")``
    ``"instant_2025-09-27"``             -> ``("instant", None, "2025-09-27")``
    Returns ``None`` if it doesn't parse.
    """
    if not isinstance(period_key, str):
        return None
    parts = period_key.split("_")
    if parts[0] == "instant" and len(parts) == 2:
        return ("instant", None, parts[1])
    if parts[0] == "duration" and len(parts) == 3:
        return ("duration", parts[1], parts[2])
    return None


def _duration_days(start: str, end: str) -> Optional[int]:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except Exception:  # noqa: BLE001 — malformed date → unclassifiable
        return None


def _infer_unit(canonical_key: str) -> str:
    if canonical_key in PER_SHARE_KEYS:
        return "USD/shares"
    if canonical_key in SHARE_COUNT_KEYS:
        return "shares"
    return "USD"


def _keep_period(
    period_type: str, start: Optional[str], end: str, want_annual: bool
) -> bool:
    """Whether a period matches the granularity we want for this filing."""
    if period_type == "instant":
        return True  # balance-sheet snapshots: keep every date
    if start is None:
        return False
    days = _duration_days(start, end)
    if days is None:
        return False
    if want_annual:
        return days >= _ANNUAL_MIN_DAYS
    return days <= _QUARTER_MAX_DAYS


def facts_from_frames(
    frames: dict[str, "object"],  # statement_type -> pandas DataFrame
    filing: FilingRef,
) -> list[FinancialFact]:
    """Build normalized facts from per-statement fact DataFrames. PURE.

    ``frames`` maps an edgartools statement type to a DataFrame with at least
    the columns ``concept``, ``numeric_value``, ``period_key``, ``is_dimensioned``.
    """
    want_annual = (filing.form_type or "").upper() == "10-K"
    # (canonical_key, period_end) -> (priority, FinancialFact); lower priority wins.
    best: dict[tuple[str, str], tuple[int, FinancialFact]] = {}

    for df in frames.values():
        if df is None or getattr(df, "empty", True):
            continue
        for row in df.to_dict("records"):
            if row.get("is_dimensioned"):
                continue  # consolidated totals only
            value = row.get("numeric_value")
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            mapped = map_concept(str(row.get("concept", "")))
            if mapped is None:
                continue
            canonical_key, statement, priority = mapped
            parsed = parse_period(row.get("period_key", ""))
            if parsed is None:
                continue
            period_type, start, end = parsed
            if not _keep_period(period_type, start, end, want_annual):
                continue

            try:
                fiscal_year = date.fromisoformat(end).year
            except Exception:  # noqa: BLE001
                continue
            fiscal_period = "FY" if want_annual else str(row.get("fiscal_period") or "Q")

            fact = FinancialFact(
                cik=filing.cik,
                ticker=filing.ticker,
                canonical_key=canonical_key,
                statement=statement,
                value=value,
                unit=_infer_unit(canonical_key),
                period_type=period_type,  # type: ignore[arg-type]
                period_end=end,
                period_start=start,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                source_concept=str(row.get("concept", "")),
                source_method="xbrl",
                filing_id=filing.filing_id,
            )
            key = (canonical_key, end)
            existing = best.get(key)
            if existing is None or priority < existing[0]:
                best[key] = (priority, fact)

    return [f for _, f in best.values()]


def extract_filing_facts(xbrl: "object", filing: FilingRef) -> list[FinancialFact]:
    """Pull the income/balance/cashflow fact frames from an edgartools ``XBRL``
    object and normalize them. Network-dependent (the XBRL was already fetched)."""
    frames: dict[str, object] = {}
    for stype in STATEMENT_TYPES:
        try:
            frames[stype] = xbrl.query().by_statement_type(stype).to_dataframe()
        except Exception as e:  # noqa: BLE001 — a missing statement shouldn't abort the rest
            logger.warning("Could not query %s for %s: %s", stype, filing.ticker, e)
    return facts_from_frames(frames, filing)
