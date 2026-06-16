"""SQLite store for the structured financial fact base.

Local, on-disk, zero-dependency (stdlib ``sqlite3``) — fits the POC's local-first
ethos. The store is the single source of truth for *numbers*; derived metrics are
computed on read by the valuation engine (never persisted, so they can't drift).

Idempotency: facts are keyed ``(ticker, canonical_key, period_end)``. The same
period is often reported by several filings (a 10-K reports two comparative prior
years). On conflict we keep the fact from the **newest filing** (latest
``filing_date``) so a restated figure supersedes the stale comparative.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Sequence

from backend.config import settings
from backend.facts.models import FinancialFact, FilingRef

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    filing_id        TEXT PRIMARY KEY,
    cik              TEXT,
    ticker           TEXT,
    form_type        TEXT,
    filing_date      TEXT,
    period_of_report TEXT,
    fiscal_year      INTEGER,
    fiscal_period    TEXT,
    accession_no     TEXT,
    source_url       TEXT
);
CREATE TABLE IF NOT EXISTS financial_facts (
    ticker         TEXT NOT NULL,
    cik            TEXT,
    canonical_key  TEXT NOT NULL,
    statement      TEXT,
    value          REAL NOT NULL,
    unit           TEXT,
    period_type    TEXT,
    period_end     TEXT NOT NULL,
    period_start   TEXT,
    fiscal_year    INTEGER,
    fiscal_period  TEXT,
    source_concept TEXT,
    source_method  TEXT,
    filing_id      TEXT,
    filing_date    TEXT,
    confidence     REAL DEFAULT 1.0,
    PRIMARY KEY (ticker, canonical_key, period_end)
);
CREATE INDEX IF NOT EXISTS idx_facts_ticker_key
    ON financial_facts (ticker, canonical_key);
"""


def _db_path() -> str:
    return getattr(settings, "facts_db_path", "./data/facts.db")


@contextmanager
def _connect():
    """Open a connection (creating the file + schema on first use). One per call;
    SQLite connections aren't thread-shareable and the file open is cheap."""
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_filing(filing: FilingRef) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO filings
               (filing_id, cik, ticker, form_type, filing_date, period_of_report,
                fiscal_year, fiscal_period, accession_no, source_url)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(filing_id) DO UPDATE SET
                 filing_date=excluded.filing_date,
                 period_of_report=excluded.period_of_report""",
            (filing.filing_id, filing.cik, filing.ticker, filing.form_type,
             filing.filing_date, filing.period_of_report, filing.fiscal_year,
             filing.fiscal_period, filing.accession_no, filing.source_url),
        )


def upsert_facts(facts: Sequence[FinancialFact], filing_date: Optional[str] = None) -> int:
    """Insert/replace facts. On a ``(ticker, canonical_key, period_end)`` conflict
    the row from the newer filing wins (or an equal/blank date overwrites). Returns
    rows written."""
    if not facts:
        return 0
    rows = [
        (f.ticker, f.cik, f.canonical_key, f.statement, f.value, f.unit,
         f.period_type, f.period_end, f.period_start, f.fiscal_year,
         f.fiscal_period, f.source_concept, f.source_method, f.filing_id,
         filing_date, f.confidence)
        for f in facts
    ]
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO financial_facts
               (ticker, cik, canonical_key, statement, value, unit, period_type,
                period_end, period_start, fiscal_year, fiscal_period,
                source_concept, source_method, filing_id, filing_date, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(ticker, canonical_key, period_end) DO UPDATE SET
                 value=excluded.value, unit=excluded.unit,
                 statement=excluded.statement, period_type=excluded.period_type,
                 period_start=excluded.period_start, fiscal_year=excluded.fiscal_year,
                 fiscal_period=excluded.fiscal_period,
                 source_concept=excluded.source_concept,
                 source_method=excluded.source_method, filing_id=excluded.filing_id,
                 filing_date=excluded.filing_date, confidence=excluded.confidence
               WHERE COALESCE(excluded.filing_date,'') >= COALESCE(financial_facts.filing_date,'')""",
            rows,
        )
    return len(rows)


def get_financials(
    ticker: str,
    metrics: Optional[Iterable[str]] = None,
    periods: Optional[int] = None,
    statement: Optional[str] = None,
) -> dict:
    """Return stored facts for ``ticker`` grouped by canonical key, newest first.

    ``metrics`` filters canonical keys; ``periods`` caps how many periods per
    metric; ``statement`` filters by bucket. Shape:
    ``{"ticker", "metrics": {key: [{period_end, fiscal_year, fiscal_period, value,
    unit, source_concept, filing_id}, ...]}}``. Empty ``metrics`` map if nothing
    is stored yet (callers should treat that as "not ingested").
    """
    ticker = (ticker or "").strip().upper()
    where = ["ticker = ?"]
    params: list = [ticker]
    metrics = list(metrics) if metrics else None
    if metrics:
        where.append(f"canonical_key IN ({','.join('?' * len(metrics))})")
        params.extend(metrics)
    if statement:
        where.append("statement = ?")
        params.append(statement)

    sql = (
        "SELECT canonical_key, period_end, period_start, fiscal_year, fiscal_period, "
        "value, unit, source_concept, source_method, filing_id, confidence "
        "FROM financial_facts WHERE " + " AND ".join(where) +
        " ORDER BY canonical_key ASC, period_end DESC"
    )
    out: dict[str, list[dict]] = {}
    with _connect() as conn:
        for r in conn.execute(sql, params):
            lst = out.setdefault(r["canonical_key"], [])
            if periods is not None and len(lst) >= periods:
                continue
            lst.append({
                "period_end": r["period_end"],
                "period_start": r["period_start"],
                "fiscal_year": r["fiscal_year"],
                "fiscal_period": r["fiscal_period"],
                "value": r["value"],
                "unit": r["unit"],
                "source_concept": r["source_concept"],
                "source_method": r["source_method"],
                "filing_id": r["filing_id"],
                "confidence": r["confidence"],
            })
    return {"ticker": ticker, "metrics": out}


def list_covered_tickers() -> list[str]:
    with _connect() as conn:
        return [r["ticker"] for r in conn.execute(
            "SELECT DISTINCT ticker FROM financial_facts ORDER BY ticker")]
