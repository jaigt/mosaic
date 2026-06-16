"""Per-segment revenue facts, with proper dimension-axis disambiguation.

A filing breaks revenue down along several XBRL dimension *axes* — product/service,
geography, operating segment — and the members of different axes must NOT be mixed
(Apple's "iPhone" and "U.S." are different breakdowns of the same total). edgartools'
``query().with_dimensions()`` exposes the axis (``dimension``) and member
(``dimension_member_label``) per fact.

v1 captures **single-axis** revenue rows only (exactly one dimension active),
grouped by axis. This deliberately skips multi-axis rows (e.g. operating-segment ×
consolidation-items) to stay unambiguous. Values are as-reported and may include
subtotals (a parent member alongside its children); we don't infer the hierarchy.
Pure core (``segments_from_records``) + a thin edgartools wrapper. No LLM.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.facts.extractor import parse_period
from backend.facts.models import FilingRef
from backend.facts.taxonomy import _strip_ns

logger = logging.getLogger(__name__)

# Friendly names for the common revenue-breakdown axes.
AXIS_LABELS = {
    "ProductOrServiceAxis": "Product/Service",
    "StatementGeographicalAxis": "Geography",
    "StatementBusinessSegmentsAxis": "Operating Segment",
    "ConsolidationItemsAxis": "Consolidation",
}

# XBRL concepts that represent (some flavor of) revenue, for segment capture.
_REVENUE_CONCEPTS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "RevenuesNetOfInterestExpense",
    "SalesRevenueNet",
}


@dataclass(frozen=True)
class SegmentFact:
    ticker: str
    axis: str            # friendly axis name, e.g. "Geography"
    member: str          # member label, e.g. "U.S."
    value: float
    unit: str
    period_end: str
    fiscal_year: int
    filing_id: str


def _axis_label(dimension: str) -> str:
    bare = _strip_ns(dimension or "")
    return AXIS_LABELS.get(bare, bare or "Segment")


def segments_from_records(records: list[dict], filing: FilingRef) -> list[SegmentFact]:
    """Build single-axis revenue segment facts from with_dimensions() records. PURE.

    A record is single-axis when exactly one ``dim_*`` column is populated
    (non-null, not the literal "nan")."""
    want_annual = (filing.form_type or "").upper() == "10-K"
    out: list[SegmentFact] = []
    for r in records:
        if not r.get("is_dimensioned"):
            continue
        if _strip_ns(str(r.get("concept", ""))) not in _REVENUE_CONCEPTS:
            continue
        active = [k for k, v in r.items()
                  if k.startswith("dim_") and v is not None and str(v).lower() != "nan"]
        if len(active) != 1:
            continue  # skip multi-axis rows (ambiguous to group)
        value = r.get("numeric_value")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        parsed = parse_period(r.get("period_key", ""))
        if parsed is None:
            continue
        period_type, start, end = parsed
        if period_type != "duration" or start is None:
            continue
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if want_annual and days < 300:
            continue
        if not want_annual and days > 120:
            continue
        member = str(r.get("dimension_member_label") or r.get("label") or "").strip()
        if not member:
            continue
        out.append(SegmentFact(
            ticker=filing.ticker, axis=_axis_label(str(r.get("dimension", ""))),
            member=member, value=value, unit="USD", period_end=end,
            fiscal_year=date.fromisoformat(end).year, filing_id=filing.filing_id,
        ))
    return out


def extract_segments(xbrl: "object", filing: FilingRef) -> list[SegmentFact]:
    """Pull dimensioned revenue facts from the XBRL and normalize to segments."""
    try:
        df = xbrl.query().by_statement_type("IncomeStatement").with_dimensions().to_dataframe()
    except Exception as e:  # noqa: BLE001
        logger.info("segment query failed for %s: %s", filing.ticker, e)
        return []
    return segments_from_records(df.to_dict("records"), filing)


# ── storage (same SQLite file as the fact base) ──────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS segment_facts (
    ticker      TEXT NOT NULL,
    axis        TEXT NOT NULL,
    member      TEXT NOT NULL,
    period_end  TEXT NOT NULL,
    fiscal_year INTEGER,
    value       REAL NOT NULL,
    unit        TEXT,
    filing_id   TEXT,
    PRIMARY KEY (ticker, axis, member, period_end)
);
"""


@contextmanager
def _connect():
    path = getattr(settings, "facts_db_path", "./data/facts.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_segments(facts: list[SegmentFact]) -> int:
    if not facts:
        return 0
    rows = [(f.ticker, f.axis, f.member, f.period_end, f.fiscal_year, f.value, f.unit, f.filing_id)
            for f in facts]
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO segment_facts
               (ticker, axis, member, period_end, fiscal_year, value, unit, filing_id)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(ticker, axis, member, period_end) DO UPDATE SET
                 value=excluded.value, fiscal_year=excluded.fiscal_year,
                 filing_id=excluded.filing_id""",
            rows,
        )
    return len(rows)


def get_segments(ticker: str, period_end: Optional[str] = None) -> dict:
    """Segment revenue for a ticker grouped by axis (latest period if unspecified).

    Returns ``{"ticker", "period_end", "axes": {axis: [{member, value}, ...]}}``,
    members sorted by value desc. Empty axes map if none stored."""
    ticker = (ticker or "").strip().upper()
    with _connect() as conn:
        if period_end is None:
            row = conn.execute(
                "SELECT MAX(period_end) AS p FROM segment_facts WHERE ticker = ?", (ticker,)
            ).fetchone()
            period_end = row["p"] if row else None
        if not period_end:
            return {"ticker": ticker, "period_end": None, "axes": {}}
        cur = conn.execute(
            "SELECT axis, member, value FROM segment_facts WHERE ticker = ? AND period_end = ? "
            "ORDER BY axis, value DESC", (ticker, period_end),
        )
        axes: dict[str, list[dict]] = {}
        for r in cur:
            axes.setdefault(r["axis"], []).append({"member": r["member"], "value": r["value"]})
    return {"ticker": ticker, "period_end": period_end, "axes": axes}
