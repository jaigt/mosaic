"""Structured financial fact base — normalized, provenance-tracked financial line
items extracted (mostly deterministically from XBRL) once at ingest, queried
cheaply at runtime. See docs/VALUATION_ENGINE_DESIGN.md."""
from backend.facts.models import FinancialFact, FilingRef
from backend.facts.extractor import extract_filing_facts, facts_from_frames
from backend.facts.store import get_financials, upsert_facts, upsert_filing

__all__ = [
    "FinancialFact",
    "FilingRef",
    "extract_filing_facts",
    "facts_from_frames",
    "get_financials",
    "upsert_facts",
    "upsert_filing",
]
