"""
Fetches SEC filings via edgartools, respecting EDGAR rate limits.
SEC policy: max 10 requests/second, must include User-Agent header.
"""
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
    quarter = _infer_quarter(document_type, filing.filing_date.month)

    metadata = {
        "ticker": ticker.upper(),
        "cik": str(company.cik),
        "document_type": document_type,
        "filing_year": filing_year,
        "filing_quarter": quarter,
        "filing_date": str(filing.filing_date),
        "accession_number": filing.accession_number,
    }
    return filing, company, metadata


def get_filing_html(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> tuple[str, dict]:
    """
    Fetch the raw HTML content of an SEC filing.

    Returns:
        (html_content, metadata) where metadata contains cik, filing_date, etc.
    """
    logger.info(f"Fetching {document_type} HTML for {ticker} (year={year})")

    filing, _company, metadata = _get_filing_object(ticker, document_type, year)
    time.sleep(_REQUEST_DELAY)

    # In edgartools 4.x, filing.html() fetches the primary document HTML directly
    html_content = filing.html()
    if not html_content:
        raise ValueError(f"Empty HTML content for {ticker} {document_type}")

    logger.info(f"Fetched {document_type} HTML for {ticker}: {len(html_content)} chars")
    return html_content, metadata


def get_filing_xbrl(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> tuple[object, dict]:
    """
    Fetch the XBRL data object for a filing.

    Returns:
        (xbrl_data, metadata) where xbrl_data is an edgartools XBRLData object
        exposing .income_statement, .balance_sheet, .cash_flow_statement, etc.

    Raises:
        ValueError if no filing is found.
        RuntimeError if the filing has no XBRL data (older filings pre-2009
        or some foreign private issuers may not have inline XBRL).
    """
    logger.info(f"Fetching {document_type} XBRL for {ticker} (year={year})")

    filing, _company, metadata = _get_filing_object(ticker, document_type, year)
    time.sleep(_REQUEST_DELAY)

    xbrl_data = filing.xbrl()
    if xbrl_data is None:
        raise RuntimeError(
            f"No XBRL data available for {ticker} {document_type} "
            f"(filing date: {metadata['filing_date']}). "
            "This is common for filings before 2009 or some foreign issuers."
        )

    logger.info(f"Fetched XBRL data for {ticker} {document_type}")
    return xbrl_data, metadata


def _infer_quarter(document_type: str, filing_month: int) -> str:
    """Infer the reporting quarter from document type and filing month."""
    if document_type == "10-K":
        return "FY"
    # 10-Q filing months roughly map to quarters
    quarter_map = {
        (1, 2, 3, 4): "Q1",
        (4, 5, 6, 7): "Q2",
        (7, 8, 9, 10): "Q3",
    }
    for months, quarter in quarter_map.items():
        if filing_month in months:
            return quarter
    return "Q4"
