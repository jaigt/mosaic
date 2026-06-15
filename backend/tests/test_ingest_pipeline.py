"""
Tests for the top-level ``ingest_filing`` orchestration: PATH A / PATH B run
concurrently, the progress callback fires the expected stages in order, PATH A
failures are fatal while PATH B failures are swallowed.

All network/LLM/storage boundaries are monkeypatched — no real EDGAR, embedding,
or LanceDB access.
"""
import threading
import time

import pytest

import backend.pipeline.ingest as ingest_mod
from backend.ingestion.parser import ParsedDocument, ParsedElement

_META = {
    "ticker": "AAPL",
    "cik": "320193",
    "document_type": "10-K",
    "filing_year": 2024,
    "filing_quarter": "FY",
    "filing_date": "2024-11-01",
}


def _patch_common(monkeypatch, captured_vectors=None):
    """Patch resolve/embed/store so only the path-fetch behavior under test runs."""
    monkeypatch.setattr(ingest_mod, "resolve_filing", lambda t, d, y: (object(), _META))
    monkeypatch.setattr(ingest_mod, "embed_texts", lambda texts: [[0.0] for _ in texts])

    def fake_upsert(chunks, vectors):
        if captured_vectors is not None:
            captured_vectors.append((chunks, vectors))
        return len(chunks)

    monkeypatch.setattr(ingest_mod, "upsert_chunks", fake_upsert)
    # Skip the LLM table-summary pass; echo raw content (batched signature).
    monkeypatch.setattr(
        ingest_mod, "summarize_tables",
        lambda tables, ticker, document_type: ["S::" + t for t in tables],
    )


def test_paths_run_concurrently(monkeypatch):
    """The HTML fetch and the XBRL fetch must overlap, not run back-to-back."""
    _patch_common(monkeypatch)
    pad = "x" * 300

    active = {"current": 0, "max": 0}
    lock = threading.Lock()

    def slow(label, ret):
        def _inner(*args, **kwargs):
            with lock:
                active["current"] += 1
                active["max"] = max(active["max"], active["current"])
            time.sleep(0.2)
            with lock:
                active["current"] -= 1
            return ret
        return _inner

    doc = ParsedDocument(elements=[ParsedElement("text", f"narrative {pad}", "Item 1")])
    monkeypatch.setattr(ingest_mod, "html_from_filing", slow("html", "<html/>"))
    monkeypatch.setattr(ingest_mod, "parse_filing_html", lambda h: doc)
    monkeypatch.setattr(ingest_mod, "xbrl_from_filing", slow("xbrl", object()))
    monkeypatch.setattr(
        ingest_mod, "parse_xbrl_statements",
        lambda x: [ParsedElement("table", f"=== IS ===\n{pad}", "Item 8", raw_html="a,b")],
    )

    start = time.monotonic()
    written = ingest_mod.ingest_filing("AAPL", "10-K")
    elapsed = time.monotonic() - start

    assert written == 2  # one narrative + one xbrl table
    assert active["max"] >= 2, "PATH A and PATH B did not overlap"
    assert elapsed < 0.35, f"paths look serial ({elapsed:.2f}s for two 0.2s fetches)"


def test_progress_callback_stages_in_order(monkeypatch):
    """on_progress fires the expected lifecycle stages, ending with done(chunks)."""
    _patch_common(monkeypatch)
    pad = "x" * 300
    doc = ParsedDocument(elements=[ParsedElement("text", f"narrative {pad}", "Item 1")])
    monkeypatch.setattr(ingest_mod, "html_from_filing", lambda f: "<html/>")
    monkeypatch.setattr(ingest_mod, "parse_filing_html", lambda h: doc)
    monkeypatch.setattr(ingest_mod, "xbrl_from_filing", lambda f: object())
    monkeypatch.setattr(ingest_mod, "parse_xbrl_statements", lambda x: [])

    events = []
    written = ingest_mod.ingest_filing("AAPL", "10-K", on_progress=events.append)

    stages = [e["stage"] for e in events]
    assert stages == [
        "resolving", "fetching", "parsing",
        "summarizing_tables", "embedding", "storing", "done",
    ]
    assert events[-1]["chunks"] == written == 1


def test_path_a_failure_is_fatal(monkeypatch):
    """A PATH A (narrative) failure must propagate — narrative is the backbone."""
    _patch_common(monkeypatch)

    def boom(filing):
        raise ValueError("EDGAR HTML fetch failed")

    monkeypatch.setattr(ingest_mod, "html_from_filing", boom)
    monkeypatch.setattr(ingest_mod, "xbrl_from_filing", lambda f: object())
    monkeypatch.setattr(ingest_mod, "parse_xbrl_statements", lambda x: [])

    with pytest.raises(ValueError, match="EDGAR HTML fetch failed"):
        ingest_mod.ingest_filing("AAPL", "10-K")


def test_path_b_failure_is_non_fatal(monkeypatch):
    """A PATH B (XBRL) failure must be swallowed; narrative still ingests."""
    _patch_common(monkeypatch)
    pad = "x" * 300
    doc = ParsedDocument(elements=[ParsedElement("text", f"narrative {pad}", "Item 1")])
    monkeypatch.setattr(ingest_mod, "html_from_filing", lambda f: "<html/>")
    monkeypatch.setattr(ingest_mod, "parse_filing_html", lambda h: doc)

    def boom(filing):
        raise RuntimeError("no XBRL for this filing")

    monkeypatch.setattr(ingest_mod, "xbrl_from_filing", boom)

    written = ingest_mod.ingest_filing("AAPL", "10-K")
    assert written == 1  # narrative chunk survived
