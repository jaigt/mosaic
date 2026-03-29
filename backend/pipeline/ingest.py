"""
Orchestrates the full ingestion pipeline for a single SEC filing:
  1. Fetch HTML from EDGAR
  2. Parse into structured elements (sections + tables)
  3. Summarize tables with fast LLM
  4. Embed text_content
  5. Upsert into LanceDB
"""
import logging
from typing import Optional

from backend.ingestion.edgar_fetcher import get_filing_html
from backend.ingestion.parser import parse_filing_html
from backend.models.schemas import DocumentChunk
from backend.pipeline.table_summarizer import summarize_table
from backend.pipeline.embedder import embed_texts
from backend.pipeline.store import upsert_chunks, generate_chunk_id

logger = logging.getLogger(__name__)

# Minimum characters for a chunk to be worth embedding
_MIN_CHUNK_LENGTH = 100


def ingest_filing(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> int:
    """
    Full pipeline: fetch → parse → summarize tables → embed → store.
    Returns the number of chunks written to LanceDB.
    """
    # Phase 1: Fetch
    html_content, meta = get_filing_html(ticker, document_type, year)

    # Phase 2: Parse
    doc = parse_filing_html(html_content)

    chunks: list[DocumentChunk] = []
    texts_to_embed: list[str] = []

    for i, element in enumerate(doc.elements):
        if len(element.content) < _MIN_CHUNK_LENGTH:
            continue

        # Phase 2b: Two-pass table strategy
        if element.element_type == "table":
            text_content = summarize_table(
                table_content=element.raw_html or element.content,
                ticker=ticker,
                document_type=document_type,
            )
            if not text_content:
                continue
            raw_payload = element.raw_html or element.content
            chunk_type = "table"
        else:
            text_content = element.content
            raw_payload = element.content
            chunk_type = "text"

        chunk = DocumentChunk(
            chunk_id=generate_chunk_id(
                ticker=meta["ticker"],
                doc_type=document_type,
                year=meta["filing_year"],
                quarter=meta["filing_quarter"],
                index=i,
            ),
            ticker=meta["ticker"],
            cik=meta["cik"],
            document_type=document_type,
            filing_year=meta["filing_year"],
            filing_quarter=meta["filing_quarter"],
            sec_item_section=element.section,
            chunk_type=chunk_type,
            text_content=text_content,
            raw_payload=raw_payload,
        )
        chunks.append(chunk)
        texts_to_embed.append(text_content)

    if not chunks:
        logger.warning(f"No usable chunks found for {ticker} {document_type} {year}")
        return 0

    # Phase 3: Embed
    logger.info(f"Embedding {len(chunks)} chunks for {ticker}")
    vectors = embed_texts(texts_to_embed)

    # Phase 3b: Store
    written = upsert_chunks(chunks, vectors)
    logger.info(f"Ingestion complete: {written} chunks stored for {ticker}")
    return written
