"""
Validation + escaping for values interpolated into LanceDB SQL-like filter
clauses (`.where(...)` / `.delete(...)`).

LanceDB's predicate parser accepts boolean tautologies, so raw f-string
interpolation of user/LLM-derived values (ticker, document_type, quarter)
allows filter bypass and unintended row deletes. Every value that reaches a
WHERE/DELETE clause must go through here: allowlist-validated where the domain
is fixed, single-quote-escaped otherwise.
"""
import datetime
import re
from typing import Optional

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_ALLOWED_DOC_TYPES = {"10-K", "10-Q", "8-K"}
_ALLOWED_QUARTERS = {"Q1", "Q2", "Q3", "Q4", "FY"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_ticker(ticker: str) -> str:
    """Normalize to uppercase and validate against a strict symbol pattern."""
    normalized = (ticker or "").strip().upper()
    if not _TICKER_RE.match(normalized):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    return normalized


def validate_doc_type(doc_type: str) -> str:
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise ValueError(f"Invalid document_type: {doc_type!r}")
    return doc_type


def validate_quarter(quarter: str) -> str:
    if quarter not in _ALLOWED_QUARTERS:
        raise ValueError(f"Invalid quarter: {quarter!r}")
    return quarter


def validate_iso_date(value: str) -> str:
    """Validate an ISO ``YYYY-MM-DD`` date string.

    Strict pattern + a real ``date.fromisoformat`` parse, so only genuine
    calendar dates pass — an injection payload can never reach the WHERE clause.
    """
    normalized = (value or "").strip()
    if not _ISO_DATE_RE.match(normalized):
        raise ValueError(f"Invalid ISO date: {value!r}")
    try:
        datetime.date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {value!r}") from exc
    return normalized


def sql_quote(value: str) -> str:
    """Single-quote a string literal, escaping embedded quotes by doubling."""
    return "'" + str(value).replace("'", "''") + "'"


def build_where_clause(
    ticker: Optional[str] = None,
    year=None,
    document_type: Optional[str] = None,
    period_of_report: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> Optional[str]:
    """
    Build a validated WHERE clause from optional metadata filters.
    Returns None when no filters are supplied. Raises ValueError on any
    value that fails validation.

    Date filters operate on the ``period_of_report`` column (ISO YYYY-MM-DD):
      * ``period_of_report`` — exact-match on the period-end date.
      * ``period_start`` / ``period_end`` — inclusive lower/upper bounds for a
        range query. Combinable with each other and with the other filters.
    All date values are strictly validated (real ISO dates only) before being
    quoted, so they are injection-safe.
    """
    conditions: list[str] = []
    if ticker:
        conditions.append(f"ticker = {sql_quote(validate_ticker(ticker))}")
    if year:
        conditions.append(f"filing_year = {int(year)}")
    if document_type:
        conditions.append(f"document_type = {sql_quote(validate_doc_type(document_type))}")
    if period_of_report:
        conditions.append(
            f"period_of_report = {sql_quote(validate_iso_date(period_of_report))}"
        )
    if period_start:
        conditions.append(
            f"period_of_report >= {sql_quote(validate_iso_date(period_start))}"
        )
    if period_end:
        conditions.append(
            f"period_of_report <= {sql_quote(validate_iso_date(period_end))}"
        )
    return " AND ".join(conditions) if conditions else None
