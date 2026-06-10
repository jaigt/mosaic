"""Tests for the cached LanceDB connection and the guarded ANN index helper.

These exercise the performance refactor in backend/pipeline/store.py:
  * get_table() must reuse a single cached connection (no reconnect per call).
  * Rows written after a get_table() call must be visible to a later
    get_table().count_rows() (write-visibility correctness — guards against a
    stale snapshot table handle).
  * maybe_create_index() must be a safe no-op on a tiny table.
"""
import lancedb
import pytest

from backend.pipeline import store
from backend.pipeline.store import (
    DocumentChunk,  # re-exported via store's imports
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point store at a throwaway lancedb path and clear any cached connection."""
    db_path = str(tmp_path / "lancedb")
    monkeypatch.setattr(store.settings, "lancedb_path", db_path)
    store._reset_db_cache()
    yield db_path
    store._reset_db_cache()


def _make_chunk(index: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=store.generate_chunk_id("AAPL", "10-K", 2023, "FY", index),
        ticker="AAPL",
        cik="0000320193",
        document_type="10-K",
        filing_year=2023,
        filing_quarter="FY",
        sec_item_section="Item 1",
        chunk_type="text",
        text_content=f"chunk {index}",
        raw_payload="{}",
    )


def _vec():
    from backend.pipeline.embedder import EMBEDDING_DIM

    return [0.1] * EMBEDDING_DIM


class TestConnectionCaching:
    def test_connect_called_once_across_calls(self, temp_db, monkeypatch):
        """lancedb.connect must run exactly once no matter how many get_table()."""
        real_connect = lancedb.connect
        calls = {"n": 0}

        def counting_connect(*args, **kwargs):
            calls["n"] += 1
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(lancedb, "connect", counting_connect)

        store.get_table()
        store.get_table()
        store.get_table()

        assert calls["n"] == 1

    def test_get_table_returns_table(self, temp_db):
        table = store.get_table()
        assert isinstance(table, lancedb.table.Table)


class TestWriteVisibility:
    def test_rows_written_after_get_table_are_visible(self, temp_db):
        """Open a table, then write rows, then a later get_table() must see them.

        This is the correctness guard: a cached snapshot table handle would
        report a stale row count here.
        """
        # Force the table (and cached connection) into existence first.
        first = store.get_table()
        assert first.count_rows() == 0

        # Write rows through the public upsert path (uses the cached connection).
        written = store.upsert_chunks([_make_chunk(0), _make_chunk(1)], [_vec(), _vec()])
        assert written == 2

        # A later get_table() must reflect the new rows.
        assert store.get_table().count_rows() == 2

    def test_same_handle_reflects_writes_via_consistency(self, temp_db):
        """Even a previously-obtained handle should see writes (strong consistency)."""
        handle = store.get_table()
        store.upsert_chunks([_make_chunk(0)], [_vec()])
        assert handle.count_rows() == 1


class TestDimValidation:
    def test_mismatched_table_dim_raises(self, temp_db):
        """Opening a table whose vector width disagrees with EMBEDDING_DIM must
        fail fast with a clear error instead of corrupting search/insert."""
        import pyarrow as pa

        wrong_dim = store.EMBEDDING_DIM + 1
        schema = pa.schema([
            pa.field("chunk_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), wrong_dim)),
        ])
        store._db().create_table(store.TABLE_NAME, schema=schema)

        with pytest.raises(RuntimeError, match="dimension mismatch"):
            store.get_table()

    def test_matching_table_dim_passes(self, temp_db):
        table = store.get_table()  # created with the correct schema
        # Re-opening validates and succeeds.
        assert store.get_table().count_rows() == table.count_rows()


class TestMaybeCreateIndex:
    def test_noop_on_tiny_table(self, temp_db):
        """On a small table, no index is created and nothing raises."""
        store.upsert_chunks([_make_chunk(0)], [_vec()])
        table = store.get_table()
        assert store.maybe_create_index(table) is False
        # Search still works (brute-force) and ingestion was unharmed.
        assert table.count_rows() == 1

    def test_never_raises(self, temp_db):
        """maybe_create_index swallows errors and returns a bool."""
        table = store.get_table()
        result = store.maybe_create_index(table)
        assert result in (True, False)
