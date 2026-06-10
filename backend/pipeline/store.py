"""
LanceDB operations: schema definition, upsert, and table management.
Data is stored locally on disk at LANCEDB_PATH.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional, Sequence

import lancedb
import pyarrow as pa

from backend.config import settings
from backend.models.schemas import DocumentChunk
from backend.pipeline.embedder import EMBEDDING_DIM
from backend.retrieval.filters import (
    sql_quote,
    validate_doc_type,
    validate_quarter,
    validate_ticker,
)

logger = logging.getLogger(__name__)

TABLE_NAME = "sec_chunks"

# Build a vector ANN index only once the table is large enough for IVF_PQ to
# train successfully. Brute-force scan is faster (and IVF_PQ training errors)
# below this size, so on the current tiny table this is a guaranteed no-op.
_INDEX_MIN_ROWS = 256

# Cached LanceDB connection. Opening a connection (lancedb.connect) is the
# expensive part — it was previously re-run on every retrieval, every upsert
# and the /filings poll (~every 30s). We cache the *connection* process-wide.
#
# Write-visibility note (lancedb 0.27.1): with the default
# read_consistency_interval=None, a once-opened Table handle is a snapshot and
# will NOT observe rows added later in the same process. We pin the cached
# connection to read_consistency_interval=timedelta(0) (strong read
# consistency) AND re-open the table on every get_table() call, so freshly
# written rows are always visible. Re-opening a table from an already-open
# connection is cheap (just reads the latest manifest); it is the connect()
# call we are eliminating.
_db_conn: Optional[lancedb.db.DBConnection] = None


def _db() -> lancedb.db.DBConnection:
    """Return a process-wide cached LanceDB connection.

    The connection is pinned to strong read consistency (interval=0) so that
    table reads always reflect writes made elsewhere in this process.
    """
    global _db_conn
    if _db_conn is None:
        _db_conn = lancedb.connect(
            settings.lancedb_path,
            read_consistency_interval=timedelta(0),
        )
    return _db_conn


def _reset_db_cache() -> None:
    """Drop the cached connection. Intended for tests that swap lancedb_path."""
    global _db_conn
    _db_conn = None

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


def _validate_vector_dim(table: lancedb.table.Table) -> None:
    """Fail fast if the configured embedding model disagrees with the table.

    EMBEDDING_DIM is derived from settings.embedding_model; the table's vector
    column width was fixed at creation time. A mismatch (e.g. the .env was
    later pointed at a different embedding model) would otherwise surface as
    confusing search/insert errors deep inside LanceDB.
    """
    try:
        field = table.schema.field("vector")
        actual = field.type.list_size
    except Exception:  # pragma: no cover - schema introspection is best-effort
        return
    if actual is not None and actual != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: table '{TABLE_NAME}' stores "
            f"{actual}-dim vectors but EMBEDDING_MODEL produces "
            f"{EMBEDDING_DIM}-dim vectors. Changing the embedding model "
            f"requires a new table + re-ingest (or restore the original "
            f"EMBEDDING_MODEL in .env)."
        )


def get_table() -> lancedb.table.Table:
    """Connect to (or create) the LanceDB table.

    Uses a cached connection (see ``_db``); the table is re-opened each call so
    that the returned handle reflects the latest committed rows.
    """
    db = _db()
    # list_tables() replaces the deprecated table_names(); it returns a
    # ListTablesResponse whose .tables is the list of names.
    if TABLE_NAME in db.list_tables().tables:
        table = db.open_table(TABLE_NAME)
        _validate_vector_dim(table)
        return table
    logger.info(f"Creating new LanceDB table '{TABLE_NAME}'")
    return db.create_table(TABLE_NAME, schema=_SCHEMA)


def maybe_create_index(table: lancedb.table.Table) -> bool:
    """Build a cosine vector ANN index once the table is large enough.

    Defensive by design:
      * No-op below ``_INDEX_MIN_ROWS`` (IVF_PQ cannot train on tiny tables and
        a brute-force scan is faster there anyway). The current ~36-row table
        therefore never triggers indexing.
      * No-op if a vector index already exists.
      * Any failure is swallowed and logged — indexing must never break
        ingestion/upsert.

    Returns True iff an index was created.
    """
    try:
        n = table.count_rows()
        if n < _INDEX_MIN_ROWS:
            return False
        # Skip if any index already covers the vector column.
        for idx in table.list_indices():
            if "vector" in getattr(idx, "columns", []):
                return False
        table.create_index(metric="cosine", vector_column_name="vector")
        logger.info(f"Created cosine vector index on '{TABLE_NAME}' ({n} rows)")
        return True
    except Exception as e:  # noqa: BLE001 — never let indexing break ingestion
        logger.warning(f"Skipping vector index creation: {e}")
        return False


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

    # Delete existing chunks for the same filing before re-inserting (idempotent).
    # Values are validated/escaped so a malformed ticker/quarter can never widen
    # the delete to other filings (boolean-tautology injection).
    if rows:
        sample = rows[0]
        table.delete(
            f"ticker = {sql_quote(validate_ticker(sample['ticker']))} "
            f"AND document_type = {sql_quote(validate_doc_type(sample['document_type']))} "
            f"AND filing_year = {int(sample['filing_year'])} "
            f"AND filing_quarter = {sql_quote(validate_quarter(sample['filing_quarter']))}"
        )

    table.add(rows)
    logger.info(f"Upserted {len(rows)} chunks into LanceDB")

    # Opportunistically build an ANN index once the table is big enough.
    # No-op on the small current table (see maybe_create_index).
    maybe_create_index(table)

    return len(rows)


def generate_chunk_id(ticker: str, doc_type: str, year: int, quarter: str, index: int) -> str:
    return f"{ticker}_{doc_type}_{year}_{quarter}_{index:05d}"
