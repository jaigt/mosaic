"""
Fetches SEC filings via edgartools, respecting EDGAR rate limits.
SEC policy: max 10 requests/second, must include User-Agent header.
"""
import datetime
import re
import time
import logging
from typing import Optional

import edgar
from edgar import Company, get_filings

from backend.config import settings

logger = logging.getLogger(__name__)

# Configure edgartools user agent (SEC requirement)
edgar.set_identity(settings.sec_user_agent)

# Minimum delay between EDGAR requests (SEC rate limit: 10 req/s)
_REQUEST_DELAY = 0.15


def _get_filing_object(ticker: str, document_type: str, year: Optional[int]):
    """
    Shared helper: resolve a Company's most-recent (or year-filtered) filing.
    Returns (filing, company, metadata_dict).

    Thin wrapper kept for backward compatibility. New callers that need both
    the HTML and the XBRL of the SAME filing should use :func:`resolve_filing`
    once and then call :func:`html_from_filing` / :func:`xbrl_from_filing`,
    which avoids re-resolving the company + filing list a second time.
    """
    filing, metadata = resolve_filing(ticker, document_type, year)
    return filing, filing.company if hasattr(filing, "company") else None, metadata


def resolve_filing(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> tuple[object, dict]:
    """
    Resolve a Company's most-recent (or year-filtered) filing exactly ONCE.

    This performs the expensive EDGAR round trips — ``Company(ticker)`` and
    ``get_filings(form=...)`` — a single time and returns the filing object
    plus its derived metadata. Callers can then extract HTML and/or XBRL from
    the SAME filing object without paying for a second resolution.

    Returns:
        (filing, metadata) where metadata contains ticker, cik, filing_date, etc.
    """
    company = Company(ticker)
    time.sleep(_REQUEST_DELAY)

    filings = company.get_filings(form=document_type)
    if not filings:
        raise ValueError(f"No {document_type} filings found for {ticker}")

    if year is not None:
        filings = [f for f in filings if f.filing_date.year == year]
        if not filings:
            raise ValueError(f"No {document_type} filing found for {ticker} in {year}")

    filing = filings[0]
    filing_year = filing.filing_date.year
    # Prefer the actual period-end date; fall back to filing date if absent.
    period_end = getattr(filing, "period_of_report", None) or filing.filing_date
    quarter = _infer_quarter(document_type, period_end)

    metadata = {
        "ticker": ticker.upper(),
        "cik": str(company.cik),
        "document_type": document_type,
        "filing_year": filing_year,
        "filing_quarter": quarter,
        "filing_date": str(filing.filing_date),
        "accession_number": filing.accession_number,
    }
    return filing, metadata


def html_from_filing(filing) -> str:
    """
    Fetch the primary-document HTML for an already-resolved filing object.

    Raises ValueError if the filing yields empty HTML.
    """
    time.sleep(_REQUEST_DELAY)
    # In edgartools 4.x, filing.html() fetches the primary document HTML directly
    html_content = filing.html()
    if not html_content:
        raise ValueError("Empty HTML content for filing")
    logger.info(f"Fetched filing HTML: {len(html_content)} chars")
    return html_content


def xbrl_from_filing(filing) -> object:
    """
    Fetch the XBRL data object for an already-resolved filing object.

    Raises:
        RuntimeError if the filing has no XBRL data (older filings pre-2009
        or some foreign private issuers may not have inline XBRL).
    """
    time.sleep(_REQUEST_DELAY)
    xbrl_data = filing.xbrl()
    if xbrl_data is None:
        raise RuntimeError(
            "No XBRL data available for filing "
            f"(filing date: {getattr(filing, 'filing_date', '?')}). "
            "This is common for filings before 2009 or some foreign issuers."
        )
    logger.info("Fetched XBRL data for filing")
    return xbrl_data


def get_filing_html(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> tuple[str, dict]:
    """
    Fetch the raw HTML content of an SEC filing.

    Thin wrapper: resolve the filing then fetch its HTML. Kept so existing
    callers are unaffected; callers needing both HTML and XBRL should prefer
    :func:`resolve_filing` + :func:`html_from_filing` to avoid a double fetch.

    Returns:
        (html_content, metadata) where metadata contains cik, filing_date, etc.
    """
    logger.info(f"Fetching {document_type} HTML for {ticker} (year={year})")
    filing, metadata = resolve_filing(ticker, document_type, year)
    html_content = html_from_filing(filing)
    logger.info(f"Fetched {document_type} HTML for {ticker}: {len(html_content)} chars")
    return html_content, metadata


def get_filing_xbrl(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> tuple[object, dict]:
    """
    Fetch the XBRL data object for a filing.

    Thin wrapper: resolve the filing then fetch its XBRL. Kept so existing
    callers are unaffected.

    Returns:
        (xbrl_data, metadata) where xbrl_data is an edgartools XBRLData object
        exposing .income_statement, .balance_sheet, .cash_flow_statement, etc.

    Raises:
        ValueError if no filing is found.
        RuntimeError if the filing has no XBRL data (older filings pre-2009
        or some foreign private issuers may not have inline XBRL).
    """
    logger.info(f"Fetching {document_type} XBRL for {ticker} (year={year})")
    filing, metadata = resolve_filing(ticker, document_type, year)
    xbrl_data = xbrl_from_filing(filing)
    logger.info(f"Fetched XBRL data for {ticker} {document_type}")
    return xbrl_data, metadata


def _calendar_quarter(month: int) -> str:
    """Map a month (1-12) to its non-overlapping calendar quarter."""
    return f"Q{(month - 1) // 3 + 1}"


def _infer_quarter(document_type: str, period_end) -> str:
    """
    Infer the reporting quarter for a filing.

    10-K -> always "FY". For a 10-Q we use the calendar quarter of the
    *period-end* date (filing.period_of_report), NOT the filing month — a 10-Q
    is filed weeks after quarter close, and the old filing-month heuristic used
    overlapping ranges that mislabeled boundary months. ``period_end`` may be a
    ``datetime.date`` or an ISO ``YYYY-MM-DD`` string; ``None`` yields "Q?".

    Note: this is the *calendar* quarter of the period-end. Companies with a
    non-calendar fiscal year (e.g. Apple, FY ends September) will have a
    calendar quarter that differs from their fiscal-quarter label. Storing the
    raw period_of_report date as metadata (future work) removes the ambiguity.
    """
    if document_type == "10-K":
        return "FY"
    if not period_end:
        return "Q?"
    if isinstance(period_end, str):
        period_end = datetime.date.fromisoformat(period_end)
    return _calendar_quarter(period_end.month)
