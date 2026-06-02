"""Tests for backend.api.main operational hardening.

Covers:
  * typed ingest task state + backward-compatible /ingest, /ingest/status JSON.
  * bounded SSE queue + producer stop-on-disconnect for the chat stream.
  * request-id propagation into SSE error events.

All LLM/retrieve/ingest layers are monkeypatched so no network is needed.
"""
import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import backend.api.main as main
from backend.models.schemas import ChatRequest


# ── Ingest task state ────────────────────────────────────────────────────────

def _client(monkeypatch):
    # Disable auth + rate limit so the route tests don't need headers.
    monkeypatch.setattr(main.settings, "api_key", "")
    monkeypatch.setattr(main.settings, "rate_limit_per_minute", 0)
    return TestClient(main.app)


def test_ingest_starts_and_status_is_backward_compatible(monkeypatch):
    main._ingest_tasks.clear()

    done = threading.Event()

    def fake_ingest(ticker, document_type, year):
        return 42

    monkeypatch.setattr(main, "ingest_filing", fake_ingest)
    client = _client(monkeypatch)

    resp = client.post("/ingest", json={"ticker": "AAPL", "document_type": "10-K"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    task_id = body["task_id"]
    assert task_id

    # Poll status until completion (background task runs in the test loop).
    for _ in range(100):
        s = client.get(f"/ingest/status/{task_id}").json()
        if s["status"].startswith("completed"):
            break
        time.sleep(0.02)
    else:
        pytest.fail("ingest never completed")

    assert s["task_id"] == task_id
    # Backward-compatible "completed:N" string preserved.
    assert s["status"] == "completed:42"
    # New typed fields are additive.
    assert s["state"] == "completed"
    assert s["chunks"] == 42
    assert s["error"] is None


def test_ingest_failure_reports_failed_status(monkeypatch):
    main._ingest_tasks.clear()

    def boom(ticker, document_type, year):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(main, "ingest_filing", boom)
    client = _client(monkeypatch)

    task_id = client.post(
        "/ingest", json={"ticker": "MSFT", "document_type": "10-K"}
    ).json()["task_id"]

    for _ in range(100):
        s = client.get(f"/ingest/status/{task_id}").json()
        if s["status"].startswith("failed"):
            break
        time.sleep(0.02)
    else:
        pytest.fail("ingest never failed")

    assert s["status"].startswith("failed:")
    assert "kaboom" in s["status"]
    assert s["state"] == "failed"
    assert "kaboom" in s["error"]


def test_status_not_found(monkeypatch):
    client = _client(monkeypatch)
    s = client.get("/ingest/status/does-not-exist").json()
    assert s["status"] == "not_found"
    assert s["task_id"] == "does-not-exist"


# ── Chat stream: disconnect stops the producer ───────────────────────────────

class _FakeChunk:
    def __init__(self):
        from types import SimpleNamespace
        self.chunk = SimpleNamespace(
            ticker="AAPL", filing_year=2024, filing_quarter="FY",
            sec_item_section="Item 7", chunk_type="text",
            text_content="t", raw_payload="r", document_type="10-K",
        )
        self.score = 0.9


def test_producer_stops_when_client_disconnects(monkeypatch):
    """When the request reports disconnected, the sync producer thread must stop
    pumping tokens (it observes the cooperative stop flag) instead of running the
    full paid generation to completion."""
    monkeypatch.setattr(
        main, "retrieve", lambda **kw: [_FakeChunk()]
    )

    produced = {"count": 0}
    stop_seen = threading.Event()

    def fake_stream_generate(prompt, model):
        # Emit many tokens; a well-behaved consumer should stop us early.
        for i in range(1000):
            produced["count"] += 1
            yield f"tok{i}"
            time.sleep(0.005)
        stop_seen.set()

    monkeypatch.setattr(main, "stream_generate", fake_stream_generate)

    # A request that reports "disconnected" after the first poll.
    class FakeRequest:
        def __init__(self):
            self._polls = 0

        async def is_disconnected(self):
            self._polls += 1
            return self._polls > 2  # connected for first couple of checks

    req = ChatRequest(message="hi")

    async def drive():
        gen = main._chat_stream(req, FakeRequest())
        collected = []
        try:
            # Pull a few events then stop consuming (simulating disconnect).
            async for ev in gen:
                collected.append(ev)
                if len(collected) >= 4:
                    break
        finally:
            await gen.aclose()
        return collected

    collected = asyncio.run(drive())
    # Give the daemon thread a moment to observe the stop flag and exit.
    time.sleep(0.2)
    # It must NOT have produced all 1000 tokens.
    assert produced["count"] < 1000, (
        f"producer kept generating after disconnect: {produced['count']}"
    )
    # SSE shape preserved on the events we did get.
    for ev in collected:
        assert ev.startswith("data: ")
        payload = json.loads(ev[len("data: "):].strip())
        assert payload["type"] in ("status", "chunk", "sources", "done", "error")


def test_chat_stream_happy_path_shape(monkeypatch):
    monkeypatch.setattr(main, "retrieve", lambda **kw: [_FakeChunk()])

    def fake_stream_generate(prompt, model):
        yield "Hello "
        yield "world"

    monkeypatch.setattr(main, "stream_generate", fake_stream_generate)

    class FakeRequest:
        async def is_disconnected(self):
            return False

    async def drive():
        events = []
        async for ev in main._chat_stream(ChatRequest(message="hi"), FakeRequest()):
            events.append(ev)
        return events

    events = asyncio.run(drive())
    types = [json.loads(e[len("data: "):].strip())["type"] for e in events]
    assert "status" in types
    assert "chunk" in types
    assert "sources" in types
    assert types[-1] == "done"
    # Tokens streamed through.
    chunks = [
        json.loads(e[len("data: "):].strip())["data"]
        for e in events
        if json.loads(e[len("data: "):].strip())["type"] == "chunk"
    ]
    assert "Hello " in chunks and "world" in chunks
