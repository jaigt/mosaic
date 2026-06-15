"""
Phase 4: Pre-filtered vector search against LanceDB.
Applies metadata filters first, then runs semantic search on the filtered subset.
"""
import logging
from typing import Optional

from backend.pipeline.store import get_table
from backend.pipeline.embedder import embed_query
from backend.models.schemas import DocumentChunk, RetrievedChunk
from backend.retrieval.filters import build_where_clause
from backend.retrieval.query_parser import extract_filters
from backend.retrieval.hybrid import fuse_candidates
from backend.retrieval.rerank import diversify

logger = logging.getLogger(__name__)

# How many candidates to over-fetch from the vector store before hybrid fusion
# and diversification narrow back down to top_k.
_DEFAULT_OVERFETCH = 4


def retrieve(
    query: str,
    top_k: int = 5,
    ticker: Optional[str] = None,
    year: Optional[int] = None,
    document_type: Optional[str] = None,
    period_of_report: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    hybrid: bool = True,
    diversify_results: bool = True,
    overfetch: int = _DEFAULT_OVERFETCH,
    mmr_lambda: float = 0.7,
) -> list[RetrievedChunk]:
    """
    1. Extract metadata filters from query (unless overrides are provided).
    2. Pre-filter LanceDB rows using SQL-like WHERE clause.
    3. Over-fetch vector candidates, optionally fuse with a lexical ranking
       (RRF) and diversify (MMR) before narrowing to top_k.
    4. Return top_k RetrievedChunk objects.

    The hybrid/diversify steps are pure post-processing over the fetched
    candidate set (no extra index, no extra network call). They default on but
    can be disabled per call for backward-compatible pure-vector behaviour.
    """
    # Use explicit overrides first, fall back to LLM-extracted filters
    auto_filters = extract_filters(query)
    effective_ticker = ticker or auto_filters.get("ticker")
    effective_year = year or auto_filters.get("year")
    effective_doc_type = document_type or auto_filters.get("document_type")

    # Build a validated/escaped WHERE clause. Invalid filter values (e.g. an
    # LLM-hallucinated ticker, or an injection attempt) are dropped rather than
    # interpolated raw.
    try:
        where_clause = build_where_clause(
            ticker=effective_ticker,
            year=effective_year,
            document_type=effective_doc_type,
            period_of_report=period_of_report,
            period_start=period_start,
            period_end=period_end,
        )
    except ValueError as e:
        logger.warning(f"Ignoring invalid retrieval filters: {e}")
        where_clause = None
    logger.info(f"Retrieving: query='{query[:60]}' filters={where_clause} top_k={top_k}")

    # Embed the query
    query_vector = embed_query(query)

    # Over-fetch candidates so the pure RRF + MMR steps have material to work
    # with; we always fetch at least top_k. With both post-steps disabled this
    # collapses to the original top_k vector fetch.
    fetch_k = top_k * overfetch if (hybrid or diversify_results) else top_k
    fetch_k = max(fetch_k, top_k)

    # Execute search
    table = get_table()
    search = table.search(query_vector).limit(fetch_k)
    if where_clause:
        search = search.where(where_clause)

    results = search.to_list()

    candidates = _rows_to_retrieved(results)

    # Step: hybrid lexical fusion over the candidate set (pure, in-memory).
    if hybrid and candidates:
        candidates = _apply_hybrid(query, candidates)

    # Step: MMR diversification to suppress near-duplicate chunks (pure).
    if diversify_results and candidates:
        candidates = _apply_diversify(candidates, top_k, mmr_lambda)

    retrieved = candidates[:top_k]
    logger.info(f"Retrieved {len(retrieved)} chunks (from {len(candidates)} candidates)")
    return retrieved


def _rows_to_retrieved(results: list) -> list[RetrievedChunk]:
    """Map raw LanceDB rows to RetrievedChunk objects. Pure given rows."""
    retrieved: list[RetrievedChunk] = []
    for row in results:
        chunk = DocumentChunk(
            chunk_id=row["chunk_id"],
            ticker=row["ticker"],
            cik=row["cik"],
            document_type=row["document_type"],
            filing_year=row["filing_year"],
            filing_quarter=row["filing_quarter"],
            # "" (the stored sentinel for "unset") normalizes back to None.
            period_of_report=row.get("period_of_report") or None,
            sec_item_section=row["sec_item_section"],
            chunk_type=row["chunk_type"],
            text_content=row["text_content"],
            raw_payload=row["raw_payload"],
        )
        retrieved.append(RetrievedChunk(chunk=chunk, score=row.get("_distance", 0.0)))
    return retrieved


def _apply_hybrid(query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Fuse vector order with a lexical ranking via RRF. Pure reordering."""
    items = [
        {"id": c.chunk.chunk_id, "text": c.chunk.text_content, "_chunk": c}
        for c in candidates
    ]
    fused = fuse_candidates(query, items, text_key="text", id_key="id")
    return [item["_chunk"] for item in fused]


def _apply_diversify(
    candidates: list[RetrievedChunk], top_k: int, mmr_lambda: float
) -> list[RetrievedChunk]:
    """MMR-diversify an already-ranked candidate list. Pure reordering."""
    items = [
        {"id": c.chunk.chunk_id, "text": c.chunk.text_content, "_chunk": c}
        for c in candidates
    ]
    # Diversify a slightly larger window than top_k so reordering has headroom.
    selected = diversify(items, top_k=max(top_k, len(items)), lambda_=mmr_lambda, text_key="text")
    return [item["_chunk"] for item in selected]
