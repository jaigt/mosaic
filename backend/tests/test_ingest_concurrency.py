"""
Tests for the batched, parallel table-summarization pass in the ingestion
pipeline (``_elements_to_chunks``).

The pass groups tables into batches (``_TABLE_BATCH_SIZE`` per LLM call) and runs
the batches concurrently under a token bucket. These tests monkeypatch
``summarize_tables`` so no real LLM/network is involved and assert:
  (a) results are reassembled in original element order,
  (b) batches run concurrently (total wall time << serial sum),
  (c) a raising summarizer still falls back to each element's raw text,
  (d) batching collapses N tables into ceil(N/batch_size) LLM calls.
"""
import threading
import time

import pytest

import backend.pipeline.ingest as ingest_mod
from backend.ingestion.parser import ParsedElement


_META = {
    "ticker": "AAPL",
    "cik": "320193",
    "filing_year": 2024,
    "filing_quarter": "FY",
}


def _make_elements(n_tables: int) -> list[ParsedElement]:
    """A mix of text and table elements long enough to pass _MIN_CHUNK_LENGTH."""
    pad = "x" * 300
    elements: list[ParsedElement] = []
    for i in range(n_tables):
        elements.append(
            ParsedElement(
                element_type="text",
                content=f"narrative-{i} {pad}",
                section=f"Item {i}",
            )
        )
        elements.append(
            ParsedElement(
                element_type="table",
                content=f"RAWTABLE-{i} {pad}",
                section=f"Item {i}",
                raw_html=f"<table>T{i}</table>",
            )
        )
    return elements


def test_table_summaries_reassembled_in_order(monkeypatch):
    """Summaries must map back to the correct element index regardless of the
    order the parallel batches happen to finish in."""
    elements = _make_elements(4)
    # One table per batch so completion order can be scrambled per table.
    monkeypatch.setattr(ingest_mod, "_TABLE_BATCH_SIZE", 1)
    monkeypatch.setattr(ingest_mod, "_clean_table_html", lambda h: h)

    def fake_summarize_tables(tables, ticker, document_type):
        out = []
        for tid in tables:  # tid == raw_html passed through _clean_table_html
            # Sleep longer for earlier tables so completion order reverses.
            if "T0" in tid:
                time.sleep(0.15)
            elif "T1" in tid:
                time.sleep(0.10)
            elif "T2" in tid:
                time.sleep(0.05)
            out.append(f"SUMMARY::{tid}")
        return out

    monkeypatch.setattr(ingest_mod, "summarize_tables", fake_summarize_tables)

    chunks, texts = ingest_mod._elements_to_chunks(
        elements=elements,
        meta=_META,
        document_type="10-K",
        ticker="AAPL",
    )

    assert len(chunks) == len(elements)
    for i, (chunk, text) in enumerate(zip(chunks, texts)):
        assert chunk.text_content == text
        if i % 2 == 0:
            assert chunk.chunk_type == "text"
            assert chunk.text_content.startswith(f"narrative-{i // 2}")
        else:
            assert chunk.chunk_type == "table"
            assert chunk.text_content == f"SUMMARY::<table>T{i // 2}</table>"
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id.endswith(f"{i:05d}")


def test_batches_run_concurrently(monkeypatch):
    """Total wall time must be far below the serial sum of per-batch sleeps."""
    n = 5
    elements = [
        ParsedElement(
            element_type="table",
            content="RAW " + "x" * 300,
            section="Item 8",
            raw_html=f"<table>T{i}</table>",
        )
        for i in range(n)
    ]
    per_call = 0.2

    active = {"current": 0, "max": 0}
    lock = threading.Lock()

    def fake_summarize_tables(tables, ticker, document_type):
        with lock:
            active["current"] += 1
            active["max"] = max(active["max"], active["current"])
        time.sleep(per_call)
        with lock:
            active["current"] -= 1
        return ["S::" + t for t in tables]

    # One table per batch → n concurrent batches.
    monkeypatch.setattr(ingest_mod, "_TABLE_BATCH_SIZE", 1)
    monkeypatch.setattr(ingest_mod, "summarize_tables", fake_summarize_tables)
    monkeypatch.setattr(ingest_mod, "_clean_table_html", lambda h: h)
    monkeypatch.setattr(ingest_mod, "_TABLE_RPM", 100000)

    start = time.monotonic()
    chunks, texts = ingest_mod._elements_to_chunks(
        elements=elements,
        meta=_META,
        document_type="10-K",
        ticker="AAPL",
    )
    elapsed = time.monotonic() - start

    serial = n * per_call  # 1.0s
    assert elapsed < serial * 0.7, (
        f"expected concurrent (<{serial * 0.7:.2f}s), got {elapsed:.2f}s"
    )
    assert active["max"] >= 2, "batches did not overlap"
    assert len(chunks) == n
    for i, chunk in enumerate(chunks):
        assert chunk.text_content == f"S::<table>T{i}</table>"


def test_batching_reduces_call_count(monkeypatch):
    """N tables with batch_size B must produce ceil(N/B) LLM calls, not N."""
    n = 12
    elements = [
        ParsedElement(
            element_type="table",
            content="RAW " + "x" * 300,
            section="Item 8",
            raw_html=f"<table>T{i}</table>",
        )
        for i in range(n)
    ]
    calls = {"count": 0, "sizes": []}
    lock = threading.Lock()

    def fake_summarize_tables(tables, ticker, document_type):
        with lock:
            calls["count"] += 1
            calls["sizes"].append(len(tables))
        return ["S::" + t for t in tables]

    monkeypatch.setattr(ingest_mod, "_TABLE_BATCH_SIZE", 6)
    monkeypatch.setattr(ingest_mod, "summarize_tables", fake_summarize_tables)
    monkeypatch.setattr(ingest_mod, "_clean_table_html", lambda h: h)
    monkeypatch.setattr(ingest_mod, "_TABLE_RPM", 100000)

    chunks, _ = ingest_mod._elements_to_chunks(
        elements=elements, meta=_META, document_type="10-K", ticker="AAPL",
    )

    assert calls["count"] == 2, f"expected 2 batched calls, got {calls['count']}"
    assert sorted(calls["sizes"]) == [6, 6]
    assert len(chunks) == n
    for i, chunk in enumerate(chunks):
        assert chunk.text_content == f"S::<table>T{i}</table>"


def test_failed_summary_falls_back_to_raw_text(monkeypatch):
    """A raising summarizer must yield each element's raw content, not crash."""
    elements = [
        ParsedElement(
            element_type="table",
            content="RAW-CONTENT-0 " + "y" * 300,
            section="Item 8",
            raw_html="<table>T0</table>",
        ),
        ParsedElement(
            element_type="table",
            content="RAW-CONTENT-1 " + "y" * 300,
            section="Item 8",
            raw_html="<table>T1</table>",
        ),
    ]

    def boom(tables, ticker, document_type):
        raise RuntimeError("rate limit exceeded")

    monkeypatch.setattr(ingest_mod, "summarize_tables", boom)
    monkeypatch.setattr(ingest_mod, "_clean_table_html", lambda h: h)

    chunks, texts = ingest_mod._elements_to_chunks(
        elements=elements,
        meta=_META,
        document_type="10-K",
        ticker="AAPL",
    )

    assert len(chunks) == 2
    assert chunks[0].text_content == elements[0].content
    assert chunks[1].text_content == elements[1].content
    assert all(c.chunk_type == "table" for c in chunks)
