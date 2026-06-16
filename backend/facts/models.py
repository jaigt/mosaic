"""Data models for the structured financial fact base.

A ``FinancialFact`` is one normalized line item for one company, one period —
e.g. AAPL revenue for FY2025 = 416,161,000,000 USD, sourced from the XBRL concept
``us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax``. Facts carry full
provenance (where the number came from) so every figure is auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

PeriodType = Literal["duration", "instant"]
SourceMethod = Literal["xbrl", "llm", "computed"]


@dataclass(frozen=True)
class FinancialFact:
    """One normalized financial figure for a (company, period, line item).

    ``canonical_key`` is our controlled vocabulary (e.g. ``revenue``); the messy
    XBRL tag it came from is kept in ``source_concept`` for auditability.
    """

    cik: str
    ticker: str
    canonical_key: str            # our taxonomy key, e.g. "revenue"
    statement: str                # income_statement | balance_sheet | cash_flow
    value: float
    unit: str                     # e.g. "USD", "USD/shares", "shares"
    period_type: PeriodType
    period_end: str               # ISO date; the as-of date (instant) or period end (duration)
    period_start: Optional[str]   # ISO date for duration facts; None for instant
    fiscal_year: int
    fiscal_period: str            # "FY" | "Q1".."Q4"
    source_concept: str           # the XBRL concept tag (or "" for computed)
    source_method: SourceMethod
    filing_id: str                # accession-derived id linking back to the filing
    confidence: float = 1.0       # 1.0 = deterministic XBRL; lower for llm/flagged


@dataclass(frozen=True)
class FilingRef:
    """Identifies the filing a set of facts was extracted from."""

    filing_id: str
    cik: str
    ticker: str
    form_type: str                # "10-K" | "10-Q"
    filing_date: Optional[str]
    period_of_report: Optional[str]
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]
    accession_no: Optional[str] = None
    source_url: Optional[str] = None
