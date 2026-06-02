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

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    top_k: int = 5,
    ticker: Optional[str] = None,
    year: Optional[int] = None,
    document_type: Optional[str] = None,
) -> list[RetrievedChunk]:
    """
    1. Extract metadata filters from query (unless overrides are provided).
    2. Pre-filter LanceDB rows using SQL-like WHERE clause.
    3. Run vector search on the filtered subset.
    4. Return top_k RetrievedChunk objects.
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
        )
    except ValueError as e:
        logger.warning(f"Ignoring invalid retrieval filters: {e}")
        where_clause = None
    logger.info(f"Retrieving: query='{query[:60]}' filters={where_clause} top_k={top_k}")

    # Embed the query
    query_vector = embed_query(query)

    # Execute search
    table = get_table()
    search = table.search(query_vector).limit(top_k)
    if where_clause:
        search = search.where(where_clause)

    results = search.to_list()

    retrieved: list[RetrievedChunk] = []
    for row in results:
        chunk = DocumentChunk(
            chunk_id=row["chunk_id"],
            ticker=row["ticker"],
            cik=row["cik"],
            document_type=row["document_type"],
            filing_year=row["filing_year"],
            filing_quarter=row["filing_quarter"],
            sec_item_section=row["sec_item_section"],
            chunk_type=row["chunk_type"],
            text_content=row["text_content"],
            raw_payload=row["raw_payload"],
        )
        retrieved.append(RetrievedChunk(chunk=chunk, score=row.get("_distance", 0.0)))

    logger.info(f"Retrieved {len(retrieved)} chunks")
    return retrieved
