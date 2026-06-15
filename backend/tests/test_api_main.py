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

    def fake_ingest(ticker, document_type, year, on_progress=None):
        if on_progress is not None:
            on_progress({"stage": "embedding", "chunks": 42})
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
    # Live progress stage from the ingest callback surfaces in status.
    assert s["stage"] == "embedding"
    assert s["detail"] == {"chunks": 42}


def test_ingest_failure_reports_failed_status(monkeypatch):
    main._ingest_tasks.clear()

    def boom(ticker, document_type, year, on_progress=None):
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


def test_insiders_endpoint(monkeypatch):
    from backend.holdings.models import InsiderActivity
    monkeypatch.setattr(
        main, "get_insider_activity",
        lambda ticker, limit: InsiderActivity(ticker=ticker.upper(), buys=1, bought_shares=500),
    )
    client = _client(monkeypatch)
    r = client.get("/insiders/aapl")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL" and body["buys"] == 1 and body["net_shares"] == 500


def test_institutions_endpoint(monkeypatch):
    from backend.holdings.models import FundHoldings, Holding
    fh = FundHoldings(fund="Berkshire", report_period="2026-03-31", total_value=1000,
                      total_holdings=1, holdings=[Holding("APPLE", "AAPL", "C2", 600, 3, 60.0)])
    monkeypatch.setattr(main, "get_fund_holdings", lambda fund, top: fh)
    client = _client(monkeypatch)
    r = client.get("/institutions/BRK-B")
    assert r.status_code == 200
    assert r.json()["holdings"][0]["ticker"] == "AAPL"


def test_smart_money_endpoint(monkeypatch):
    from backend.holdings.models import FundPosition, TickerOwnership
    own = TickerOwnership(
        ticker="AAPL", refreshed_at="2026-06-15T00:00:00Z",
        positions=[FundPosition("Buffett", "1", "AAPL", "APPLE", 6e10, 3e8, 22.0, "2026-03-31", "trimmed", 4e8)],
    )
    monkeypatch.setattr(main, "funds_holding_lookup", lambda ticker: own)
    client = _client(monkeypatch)
    r = client.get("/smart-money/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["positions"][0]["fund"] == "Buffett" and body["positions"][0]["change"] == "trimmed"


def test_startup_refreshes_stale_index(monkeypatch):
    """The startup hook kicks a background refresh when the index is stale."""
    monkeypatch.setattr(main.settings, "smart_money_auto_refresh", True)
    monkeypatch.setattr(main, "load_index", lambda: {"refreshed_at": ""})  # stale
    called = threading.Event()
    monkeypatch.setattr(main, "refresh_smart_money",
                        lambda: called.set() or {"funds": 1, "rows": 1})
    main._maybe_refresh_smart_money_on_startup()
    assert called.wait(timeout=2.0), "stale index did not trigger a refresh"


def test_startup_skips_fresh_index(monkeypatch):
    monkeypatch.setattr(main.settings, "smart_money_auto_refresh", True)
    monkeypatch.setattr(main, "load_index",
                        lambda: {"refreshed_at": "2999-01-01T00:00:00Z"})  # fresh
    called = {"n": 0}
    monkeypatch.setattr(main, "refresh_smart_money", lambda: called.__setitem__("n", 1))
    main._maybe_refresh_smart_money_on_startup()
    time.sleep(0.1)
    assert called["n"] == 0


def test_startup_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(main.settings, "smart_money_auto_refresh", False)
    monkeypatch.setattr(main, "refresh_smart_money",
                        lambda: pytest.fail("should not refresh when disabled"))
    main._maybe_refresh_smart_money_on_startup()


def test_smart_money_refresh_endpoint(monkeypatch):
    monkeypatch.setattr(main, "refresh_smart_money", lambda: {"funds": 3, "rows": 120, "errors": []})
    client = _client(monkeypatch)
    r = client.post("/smart-money/refresh")
    assert r.status_code == 200 and r.json()["funds"] == 3


def test_insiders_endpoint_error_is_502(monkeypatch):
    def boom(ticker, limit):
        raise RuntimeError("edgar down")
    monkeypatch.setattr(main, "get_insider_activity", boom)
    client = _client(monkeypatch)
    assert client.get("/insiders/AAPL").status_code == 502


def test_ingest_tasks_are_bounded(monkeypatch):
    """The task store evicts oldest FINISHED tasks over the cap; RUNNING tasks
    are never evicted."""
    main._ingest_tasks.clear()
    monkeypatch.setattr(main, "_MAX_INGEST_TASKS", 5)

    # Fill with finished tasks (ascending updated_at).
    for i in range(5):
        t = main.IngestTask(task_id=f"done-{i}")
        t.mark_completed(i)
        t.updated_at = 1000 + i
        main._ingest_tasks[t.task_id] = t
    # Pin one running task that must survive eviction.
    running = main.IngestTask(task_id="running")
    running.updated_at = 0  # oldest, but RUNNING
    main._ingest_tasks["running"] = running

    with main._ingest_lock:
        main._evict_ingest_tasks_locked()
        main._ingest_tasks["new"] = main.IngestTask(task_id="new")

    assert "running" in main._ingest_tasks          # never evicted
    assert "new" in main._ingest_tasks
    assert "done-0" not in main._ingest_tasks        # oldest finished evicted
    assert len(main._ingest_tasks) <= main._MAX_INGEST_TASKS + 1


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
            chunk_id="AAPL_10-K_2024_FY_00000",
            ticker="AAPL", filing_year=2024, filing_quarter="FY",
            sec_item_section="Item 7", chunk_type="text",
            text_content="t", raw_payload="r", document_type="10-K",
        )
        self.score = 0.9


def test_producer_stops_when_client_disconnects(monkeypatch):
    """When the request reports disconnected, the sync producer thread must stop
    pumping tokens (it observes the cooperative stop flag) instead of running the
    full paid generation to completion."""
    monkeypatch.setattr(main.settings, "enable_react_agent", False)
    monkeypatch.setattr(
        main, "retrieve", lambda **kw: [_FakeChunk()]
    )
    monkeypatch.setattr(main, "extract_filters", lambda q: {})

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


def test_synthesis_error_is_surfaced_to_client(monkeypatch):
    """An exception inside the synthesis producer (bad API key, retired model,
    provider outage) must reach the client as an SSE error event — not end the
    stream silently with an empty answer."""
    monkeypatch.setattr(main.settings, "enable_react_agent", False)
    monkeypatch.setattr(main, "retrieve", lambda **kw: [_FakeChunk()])
    monkeypatch.setattr(main, "extract_filters", lambda q: {})

    def broken_stream_generate(prompt, model):
        raise RuntimeError("GOOGLE_API_KEY invalid")
        yield  # pragma: no cover — make it a generator

    monkeypatch.setattr(main, "stream_generate", broken_stream_generate)

    class FakeRequest:
        async def is_disconnected(self):
            return False

    async def drive():
        events = []
        async for ev in main._chat_stream(ChatRequest(message="hi"), FakeRequest()):
            events.append(json.loads(ev[len("data: "):].strip()))
        return events

    events = asyncio.run(drive())
    types = [e["type"] for e in events]
    assert "error" in types
    error_data = next(e["data"] for e in events if e["type"] == "error")
    assert "GOOGLE_API_KEY invalid" in error_data
    assert types[-1] == "done"


def test_table_payload_truncates_on_row_boundary():
    row = "<tr><td>Revenue</td><td>$394,328</td></tr>"
    payload = "<table>" + row * 200 + "</table>"
    out = main._truncate_payload(payload, "table", limit=2000)
    assert len(out) <= 2000
    assert out.endswith("</tr>")  # never cut mid-row


def test_text_payload_truncates_plainly():
    payload = "x" * 5000
    assert main._truncate_payload(payload, "text", limit=2000) == "x" * 2000


def test_short_payload_untouched():
    assert main._truncate_payload("short", "table") == "short"


def _events(req, fake_request):
    """Drive _chat_stream to completion and return decoded event payloads."""
    async def drive():
        out = []
        async for ev in main._chat_stream(req, fake_request):
            out.append(json.loads(ev[len("data: "):].strip()))
        return out

    return asyncio.run(drive())


class _AlwaysConnected:
    async def is_disconnected(self):
        return False


def _stub_agent_llm(monkeypatch, *, filters=None, verification_status="supported"):
    """Stub the LLM-backed agent steps so the chat path makes no network call.

    These exercise the FIXED (round-5) pipeline, so pin the ReAct agent off; the
    ReAct path is covered separately (it mocks ``generate`` to drive the loop)."""
    monkeypatch.setattr(main.settings, "enable_react_agent", False)
    monkeypatch.setattr(main, "extract_filters", lambda q: dict(filters or {}))
    from backend.agent.planner import VerificationResult
    monkeypatch.setattr(
        main, "verify_answer",
        lambda answer, sources, **kw: VerificationResult(status=verification_status),
    )


def test_chat_stream_happy_path_shape(monkeypatch):
    monkeypatch.setattr(main, "retrieve", lambda **kw: [_FakeChunk()])
    _stub_agent_llm(monkeypatch)

    def fake_stream_generate(prompt, model):
        yield "Hello "
        yield "world"

    monkeypatch.setattr(main, "stream_generate", fake_stream_generate)

    events = _events(ChatRequest(message="hi"), _AlwaysConnected())
    types = [e["type"] for e in events]
    assert "status" in types
    assert "chunk" in types
    assert "sources" in types
    assert "verification" in types          # critic pass ran
    assert types[-1] == "done"
    chunks = [e["data"] for e in events if e["type"] == "chunk"]
    assert "Hello " in chunks and "world" in chunks
    verif = next(e["data"] for e in events if e["type"] == "verification")
    assert verif["status"] == "supported"


def test_chat_auto_ingests_missing_ticker(monkeypatch):
    """When the user names a ticker the corpus lacks, the agent ingests it from
    EDGAR mid-answer, emits agent_step events, and re-searches."""
    # First search returns AAPL (wrong ticker); after ingest, returns NVDA.
    calls = {"retrieve": 0, "ingest": []}

    def fake_retrieve(**kw):
        calls["retrieve"] += 1
        if calls["retrieve"] == 1:
            return [_FakeChunk()]            # AAPL — not the requested NVDA
        nvda = _FakeChunk()
        nvda.chunk.ticker = "NVDA"
        return [nvda]

    def fake_ingest(ticker, document_type, year, on_progress=None):
        calls["ingest"].append((ticker, document_type, year))
        return 50

    monkeypatch.setattr(main, "retrieve", fake_retrieve)
    monkeypatch.setattr(main, "ingest_filing", fake_ingest)
    _stub_agent_llm(monkeypatch, filters={"ticker": "NVDA"})
    monkeypatch.setattr(main, "stream_generate", lambda p, model: iter(["answer"]))

    events = _events(ChatRequest(message="How is NVDA doing?"), _AlwaysConnected())

    # It ingested NVDA and searched twice (before + after ingest).
    assert calls["ingest"] == [("NVDA", "10-K", None)]
    assert calls["retrieve"] == 2
    steps = [e["data"] for e in events if e["type"] == "agent_step"]
    kinds = [s["kind"] for s in steps]
    assert "ingest" in kinds and "retry_search" in kinds
    assert [e for e in events if e["type"] == "sources"]  # answered after ingest


def test_chat_react_path_streams_steps_and_synthesizes(monkeypatch):
    """With the ReAct agent ON (the default), the chat drives a tool loop:
    the scripted model searches then answers, agent_step events stream, and the
    accumulated sources feed the shared synthesis + verification tail."""
    monkeypatch.setattr(main.settings, "enable_react_agent", True)
    import json as _json

    # Scripted ReAct model: search once, then answer.
    actions = iter([
        _json.dumps({"tool": "search_filings", "input": {"query": "AAPL revenue", "ticker": "AAPL"}}),
        _json.dumps({"tool": "answer", "input": {}}),
    ])
    monkeypatch.setattr(main, "generate", lambda prompt, model: next(actions))
    monkeypatch.setattr(main, "retrieve", lambda **kw: [_FakeChunk()])
    from backend.agent.planner import VerificationResult
    monkeypatch.setattr(main, "verify_answer", lambda a, s, **k: VerificationResult(status="supported"))
    monkeypatch.setattr(main, "stream_generate", lambda p, model: iter(["Apple ", "revenue."]))

    events = _events(ChatRequest(message="What was AAPL revenue?"), _AlwaysConnected())
    types = [e["type"] for e in events]
    steps = [e["data"] for e in events if e["type"] == "agent_step"]
    assert any(s["kind"] == "search" for s in steps)     # tool loop ran
    assert "chunk" in types and "sources" in types and "verification" in types
    assert types[-1] == "done"
    answer = "".join(e["data"] for e in events if e["type"] == "chunk")
    assert answer == "Apple revenue."


def test_chat_react_auto_ingests_missing_ticker(monkeypatch):
    """ReAct path: model searches (empty), ingests the missing filing, searches
    again (now found), answers — streaming ingest agent_step events."""
    monkeypatch.setattr(main.settings, "enable_react_agent", True)
    import json as _json
    actions = iter([
        _json.dumps({"tool": "search_filings", "input": {"query": "NVDA", "ticker": "NVDA"}}),
        _json.dumps({"tool": "ingest_filing", "input": {"ticker": "NVDA"}}),
        _json.dumps({"tool": "search_filings", "input": {"query": "NVDA", "ticker": "NVDA"}}),
        _json.dumps({"tool": "answer", "input": {}}),
    ])
    n_search = {"n": 0}

    def fake_retrieve(**kw):
        n_search["n"] += 1
        if n_search["n"] == 1:
            return []
        nv = _FakeChunk()
        nv.chunk.ticker = "NVDA"
        return [nv]

    ingests = []
    monkeypatch.setattr(main, "generate", lambda prompt, model: next(actions))
    monkeypatch.setattr(main, "retrieve", fake_retrieve)
    monkeypatch.setattr(main, "ingest_filing", lambda ticker, document_type, year, on_progress=None: ingests.append(ticker) or 7)
    from backend.agent.planner import VerificationResult
    monkeypatch.setattr(main, "verify_answer", lambda a, s, **k: VerificationResult(status="supported"))
    monkeypatch.setattr(main, "stream_generate", lambda p, model: iter(["ok"]))

    events = _events(ChatRequest(message="How is NVDA doing?"), _AlwaysConnected())
    kinds = [e["data"]["kind"] for e in events if e["type"] == "agent_step"]
    assert ingests == ["NVDA"]
    assert "ingest" in kinds and "ingest_done" in kinds
    assert [e for e in events if e["type"] == "sources"]


def test_chat_auto_ingest_can_be_disabled(monkeypatch):
    monkeypatch.setattr(main.settings, "enable_auto_ingest", False)
    monkeypatch.setattr(main, "retrieve", lambda **kw: [_FakeChunk()])  # AAPL only
    ingested = []
    monkeypatch.setattr(
        main, "ingest_filing",
        lambda **kw: ingested.append(kw),
    )
    _stub_agent_llm(monkeypatch, filters={"ticker": "NVDA"})
    monkeypatch.setattr(main, "stream_generate", lambda p, model: iter(["answer"]))

    events = _events(ChatRequest(message="How is NVDA?"), _AlwaysConnected())
    assert ingested == []  # no auto-ingest when disabled
    assert not [e for e in events if e["type"] == "agent_step"]
