"""
Validation + escaping for values interpolated into LanceDB SQL-like filter
clauses (`.where(...)` / `.delete(...)`).

LanceDB's predicate parser accepts boolean tautologies, so raw f-string
interpolation of user/LLM-derived values (ticker, document_type, quarter)
allows filter bypass and unintended row deletes. Every value that reaches a
WHERE/DELETE clause must go through here: allowlist-validated where the domain
is fixed, single-quote-escaped otherwise.
"""
import re
from typing import Optional

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_ALLOWED_DOC_TYPES = {"10-K", "10-Q", "8-K"}
_ALLOWED_QUARTERS = {"Q1", "Q2", "Q3", "Q4", "FY"}


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


def sql_quote(value: str) -> str:
    """Single-quote a string literal, escaping embedded quotes by doubling."""
    return "'" + str(value).replace("'", "''") + "'"


def build_where_clause(
    ticker: Optional[str] = None,
    year=None,
    document_type: Optional[str] = None,
) -> Optional[str]:
    """
    Build a validated WHERE clause from optional metadata filters.
    Returns None when no filters are supplied. Raises ValueError on any
    value that fails validation.
    """
    conditions: list[str] = []
    if ticker:
        conditions.append(f"ticker = {sql_quote(validate_ticker(ticker))}")
    if year:
        conditions.append(f"filing_year = {int(year)}")
    if document_type:
        conditions.append(f"document_type = {sql_quote(validate_doc_type(document_type))}")
    return " AND ".join(conditions) if conditions else None
