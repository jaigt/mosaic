"""Integration-ish tests for retrieve() wiring of hybrid + diversify, with the
embedder and LanceDB table monkeypatched so no network / no vector store is hit.
Verifies the pure post-processing pipeline and backward-compatible behaviour.
"""
import backend.retrieval.retriever as retriever_mod


def _row(chunk_id, text, distance):
    return {
        "chunk_id": chunk_id,
        "ticker": "AAPL",
        "cik": "0000320193",
        "document_type": "10-K",
        "filing_year": 2023,
        "filing_quarter": "FY",
        "sec_item_section": "Item 7: MD&A",
        "chunk_type": "text",
        "text_content": text,
        "raw_payload": text,
        "_distance": distance,
    }


class _FakeSearch:
    def __init__(self, rows):
        self._rows = rows

    def limit(self, n):
        self._limit = n
        return self

    def where(self, clause):
        return self

    def to_list(self):
        return self._rows[: getattr(self, "_limit", len(self._rows))]


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def search(self, vector):
        return _FakeSearch(self._rows)


def _patch(monkeypatch, rows):
    monkeypatch.setattr(retriever_mod, "embed_query", lambda q: [0.0, 0.1, 0.2])
    monkeypatch.setattr(retriever_mod, "get_table", lambda: _FakeTable(rows))
    # Avoid any LLM filter-extraction call.
    monkeypatch.setattr(retriever_mod, "extract_filters", lambda q: {})


def test_retrieve_returns_top_k(monkeypatch):
    rows = [_row(f"c{i}", f"unique chunk text number {i}", i * 0.1) for i in range(12)]
    _patch(monkeypatch, rows)
    out = retriever_mod.retrieve("revenue growth", top_k=5)
    assert len(out) == 5
    assert all(hasattr(c, "chunk") for c in out)


def test_retrieve_suppresses_near_duplicates(monkeypatch):
    # Two identical chunks rank best by vector; diversification should keep only
    # one near the top and surface a distinct chunk instead.
    rows = [
        _row("dup1", "gross margin expanded materially this year", 0.01),
        _row("dup2", "gross margin expanded materially this year", 0.02),
        _row("diverse", "litigation reserves rose due to new lawsuits", 0.03),
    ]
    _patch(monkeypatch, rows)
    out = retriever_mod.retrieve("margin", top_k=2)
    ids = [c.chunk.chunk_id for c in out]
    assert "diverse" in ids  # a distinct chunk made the cut
    assert not ("dup1" in ids and "dup2" in ids)  # both duplicates not kept


def test_retrieve_hybrid_promotes_lexical_match(monkeypatch):
    # Lexically strong chunk ranked last by vector should be pulled up.
    rows = [
        _row("a", "general overview of the business and strategy", 0.01),
        _row("b", "competition and broad market risks", 0.02),
        _row("c", "deferred revenue recognition policy detail", 0.03),
    ]
    _patch(monkeypatch, rows)
    out = retriever_mod.retrieve(
        "deferred revenue recognition policy", top_k=3, diversify_results=False
    )
    ids = [c.chunk.chunk_id for c in out]
    assert ids.index("c") < ids.index("b")


def test_retrieve_backward_compatible_pure_vector(monkeypatch):
    # With both post-steps off, results follow raw vector order and length top_k.
    rows = [_row(f"c{i}", f"text {i}", i * 0.1) for i in range(8)]
    _patch(monkeypatch, rows)
    out = retriever_mod.retrieve(
        "anything", top_k=3, hybrid=False, diversify_results=False
    )
    assert [c.chunk.chunk_id for c in out] == ["c0", "c1", "c2"]
