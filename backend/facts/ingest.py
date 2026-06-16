"""Deterministic, LLM-free fact ingestion for a single ticker.

The full narrative ingest (`pipeline.ingest.ingest_filing`) also populates the
fact base, but it runs the expensive table-summary LLM pass. The fact base only
needs XBRL — which is deterministic — so the watchlist (and any caller that just
wants the numbers) can populate facts directly from EDGAR without a model.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def ensure_facts(ticker: str, document_type: str = "10-K", *, force: bool = False) -> int:
    """Extract + store the financial fact base for ``ticker`` from its latest
    filing's XBRL, unless we already have facts for it. Deterministic (no LLM).
    Best-effort: returns 0 (never raises) if the filing/XBRL is unavailable.

    ``force`` re-extracts even when facts already exist (e.g. a refresh).
    """
    from backend.facts.store import get_financials, upsert_facts, upsert_filing

    ticker = (ticker or "").strip().upper()
    if not ticker:
        return 0
    if not force and get_financials(ticker).get("metrics"):
        return 0  # already attempted/have facts for this ticker

    try:
        from backend.facts.extractor import extract_filing_facts
        from backend.facts.models import FilingRef
        from backend.facts.validator import flag_low_confidence
        from backend.ingestion.edgar_fetcher import resolve_filing, xbrl_from_filing

        filing, meta = resolve_filing(ticker, document_type, None)
        xbrl_data = xbrl_from_filing(filing)
        accession = str(getattr(filing, "accession_no", None)
                        or getattr(filing, "accession_number", None) or "")
        filing_date = str(meta.get("filing_date") or getattr(filing, "filing_date", "") or "")
        ref = FilingRef(
            filing_id=accession or f"{ticker}-{document_type}-{meta.get('filing_year')}",
            cik=str(meta.get("cik") or getattr(filing, "cik", "") or ""),
            ticker=ticker, form_type=document_type, filing_date=filing_date,
            period_of_report=meta.get("period_of_report"), fiscal_year=meta.get("filing_year"),
            fiscal_period="FY" if document_type == "10-K" else None, accession_no=accession or None,
        )
        facts = flag_low_confidence(extract_filing_facts(xbrl_data, ref))
        if not facts:
            return 0
        upsert_filing(ref)
        n = upsert_facts(facts, filing_date=filing_date)
        try:  # segments are a bonus — never let them break fact ingestion
            from backend.facts.segments import extract_segments, upsert_segments
            upsert_segments(extract_segments(xbrl_data, ref))
        except Exception as e:  # noqa: BLE001
            logger.info("segment extraction skipped for %s: %s", ticker, e)
        return n
    except Exception as e:  # noqa: BLE001 — facts-only ingest is best-effort
        logger.info("ensure_facts(%s) skipped: %s", ticker, e)
        return 0
