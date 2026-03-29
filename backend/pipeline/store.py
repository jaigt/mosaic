"""
LanceDB operations: schema definition, upsert, and table management.
Data is stored locally on disk at LANCEDB_PATH.
"""
import logging
import uuid
from typing import Sequence

import lancedb
import pyarrow as pa

from backend.config import settings
from backend.models.schemas import DocumentChunk
from backend.pipeline.embedder import EMBEDDING_DIM

logger = logging.getLogger(__name__)

TABLE_NAME = "sec_chunks"

# PyArrow schema matching DocumentChunk + vector field
_SCHEMA = pa.schema([
    pa.field("chunk_id", pa.string()),
    pa.field("ticker", pa.string()),
    pa.field("cik", pa.string()),
    pa.field("document_type", pa.string()),
    pa.field("filing_year", pa.int32()),
    pa.field("filing_quarter", pa.string()),
    pa.field("sec_item_section", pa.string()),
    pa.field("chunk_type", pa.string()),
    pa.field("text_content", pa.string()),
    pa.field("raw_payload", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
])


def get_table() -> lancedb.table.Table:
    """Connect to (or create) the LanceDB table."""
    db = lancedb.connect(settings.lancedb_path)
    if TABLE_NAME in db.table_names():
        return db.open_table(TABLE_NAME)
    logger.info(f"Creating new LanceDB table '{TABLE_NAME}'")
    return db.create_table(TABLE_NAME, schema=_SCHEMA)


def upsert_chunks(chunks: Sequence[DocumentChunk], vectors: Sequence[list[float]]) -> int:
    """
    Upsert chunks into LanceDB. Overwrites any existing chunk with the same chunk_id.
    Returns the number of rows written.
    """
    if not chunks:
        return 0

    table = get_table()

    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "ticker": chunk.ticker,
            "cik": chunk.cik,
            "document_type": chunk.document_type,
            "filing_year": chunk.filing_year,
            "filing_quarter": chunk.filing_quarter,
            "sec_item_section": chunk.sec_item_section,
            "chunk_type": chunk.chunk_type,
            "text_content": chunk.text_content,
            "raw_payload": chunk.raw_payload,
            "vector": vec,
        }
        for chunk, vec in zip(chunks, vectors)
    ]

    # Delete existing chunks for the same filing before re-inserting (idempotent)
    if rows:
        sample = rows[0]
        table.delete(
            f"ticker = '{sample['ticker']}' "
            f"AND document_type = '{sample['document_type']}' "
            f"AND filing_year = {sample['filing_year']} "
            f"AND filing_quarter = '{sample['filing_quarter']}'"
        )

    table.add(rows)
    logger.info(f"Upserted {len(rows)} chunks into LanceDB")
    return len(rows)


def generate_chunk_id(ticker: str, doc_type: str, year: int, quarter: str, index: int) -> str:
    return f"{ticker}_{doc_type}_{year}_{quarter}_{index:05d}"
