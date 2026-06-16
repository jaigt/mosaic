"""
FastAPI backend — the interface layer between the Python RAG engine and the frontend.
Endpoints:
  POST /ingest       — trigger ingestion of an SEC filing into LanceDB
  POST /chat         — conversational query with streaming SSE response
  POST /retrieve     — raw retrieval (useful for debugging/citation display)
  GET  /health       — health check
"""
import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.api.observability import (
    get_request_id,
    install_request_id_middleware,
    log_event,
)
from backend.api.security import enforce_rate_limit, require_api_key
from backend.config import settings
from backend.models.schemas import ChatRequest, IngestRequest, QueryRequest
from backend.agent import ReactAgent, plan_auto_ingest, verify_answer
from backend.holdings import get_fund_holdings, get_insider_activity
from backend.holdings import funds_holding as funds_holding_lookup
from backend.holdings import refresh as refresh_smart_money
from backend.holdings.superinvestors import index_is_stale, load_index
from backend.pipeline.ingest import ingest_filing
from backend.pipeline.llm import generate, stream_generate, supports_native_tools
from backend.pipeline.store import get_table
from backend.retrieval.query_parser import extract_filters
from backend.retrieval.reformulate import condense_query
from backend.retrieval.retriever import retrieve
from backend.facts.store import get_financials as _get_financials
from backend.valuation import compute_metrics, compute_valuation, get_price_snapshot
from backend.valuation.summary import format_fundamentals, format_valuation

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _has_core_financials(fin: dict) -> bool:
    """Whether the fact base has the income-statement spine. Banks/insurers and
    other non-standard filers extract sparse facts (no 'revenue' concept), so the
    tools should route to prose search rather than present a misleading skeleton."""
    return "revenue" in (fin.get("metrics") or {})


_LOW_COVERAGE_MSG = (
    "{t} is in the corpus but core income-statement items (e.g. revenue) aren't "
    "mapped — typically a bank/insurer or non-standard filer the structured "
    "taxonomy doesn't cover yet. Use search_filings for its figures instead."
)


def _financials_tool(ticker: str) -> str:
    """Agent tool: authoritative fundamentals + ratios from the fact base."""
    fin = _get_financials(ticker)
    if not fin.get("metrics"):
        return (f"No structured financials for {ticker} yet — ingest its 10-K "
                "first, then ask again.")
    if not _has_core_financials(fin):
        return _LOW_COVERAGE_MSG.format(t=ticker)
    return format_fundamentals(fin, compute_metrics(fin))


def _valuation_tool(ticker: str) -> str:
    """Agent tool: multiples (with a live price) + a transparent DCF range."""
    fin = _get_financials(ticker)
    if not fin.get("metrics"):
        return f"No structured financials for {ticker} yet — ingest its 10-K first."
    if not _has_core_financials(fin):
        return _LOW_COVERAGE_MSG.format(t=ticker)
    snap = get_price_snapshot(ticker) or {}
    val = compute_valuation(fin, price=snap.get("price"),
                            shares_outstanding=snap.get("shares_outstanding"))
    return format_valuation(val)


def _thesis_tool(ticker: str) -> str:
    """Agent tool: a deterministic bull/bear thesis scaffold (signals derived from
    the fact base + valuation) for the model to narrate + add qualitative color."""
    from backend.valuation import derive_signals, format_thesis
    fin = _get_financials(ticker)
    if not fin.get("metrics"):
        return f"No structured financials for {ticker} yet — ingest its 10-K first."
    if not _has_core_financials(fin):
        return _LOW_COVERAGE_MSG.format(t=ticker)
    metrics = compute_metrics(fin)
    snap = get_price_snapshot(ticker) or {}
    val = compute_valuation(fin, price=snap.get("price"),
                            shares_outstanding=snap.get("shares_outstanding"))
    signals = derive_signals(metrics, val)
    return format_thesis(ticker, metrics, val, signals)

# Max tokens buffered between the (paid) producer thread and the SSE consumer.
# Keeps memory bounded and lets the producer block (and thus notice a stop
# signal) instead of racing ahead of a slow/disconnected client.
_SSE_QUEUE_MAXSIZE = 64
# How often the stream re-checks whether the client has disconnected (seconds).
_DISCONNECT_POLL_INTERVAL = 0.25


def _maybe_refresh_smart_money_on_startup() -> None:
    """If enabled and the smart-money index is missing/stale, rebuild it in a
    background thread (13Fs refile quarterly). Never blocks startup or raises."""
    if not settings.smart_money_auto_refresh:
        return
    try:
        idx = load_index()
        if not index_is_stale(idx.get("refreshed_at", ""), settings.smart_money_stale_days):
            return
    except Exception:  # pragma: no cover - defensive
        pass

    def _bg() -> None:
        try:
            result = refresh_smart_money()
            log_event("INFO", "smart_money_auto_refreshed",
                      funds=result.get("funds"), rows=result.get("rows"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Startup smart-money refresh failed: {e}")

    threading.Thread(target=_bg, daemon=True).start()
    log_event("INFO", "smart_money_refresh_scheduled")


@asynccontextmanager
async def _lifespan(app: "FastAPI"):
    # Startup: self-heal a stale superinvestor index without blocking readiness.
    _maybe_refresh_smart_money_on_startup()
    yield


app = FastAPI(title="Mosaic API", version="0.1.0", lifespan=_lifespan)

# Request-ID middleware first so every downstream log carries the id.
install_request_id_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_SYNTHESIS_SYSTEM_PROMPT = """\
You are an expert value investing analyst with deep knowledge of SEC filings. \
You are given retrieved excerpts from real SEC filings to answer the user's question.

Rules:
- Base your answer strictly on the provided SOURCE DOCUMENTS.
- Always cite which filing (ticker, year, section) each claim comes from using [1], [2], etc.
- If the sources do not contain enough information to answer fully, say so explicitly.
- Be concise and precise. Avoid filler text.

Generative UI (Financial Charts):
- If the user asks for a comparison of numbers (e.g., revenue over years, net income across tickers) and you have the data, you MUST include a chart in your response.
- Single series (one metric over time) — use a "value" key:
<chart>
{
  "type": "bar",
  "title": "Revenue (Billions)",
  "data": [
    {"name": "2022", "value": 117.1},
    {"name": "2023", "value": 125.4},
    {"name": "2024", "value": 130.2}
  ]
}
</chart>
- Multiple series (compare companies/metrics) — one key per series on each row, and list the series:
<chart>
{
  "type": "line",
  "title": "Revenue Comparison (Billions)",
  "data": [
    {"name": "2023", "AAPL": 383.3, "MSFT": 211.9},
    {"name": "2024", "AAPL": 391.0, "MSFT": 245.1}
  ],
  "series": ["AAPL", "MSFT"]
}
</chart>
- "type" may be "bar" (default), "line", or "area". Prefer "line"/"area" for trends over time, "bar" for point-in-time comparisons.
- Use values consistent in units; put the unit in the title. Always continue with your textual analysis AFTER the chart tag if needed.
"""


@app.get("/health")
def health():
    return {"status": "ok", "models": {
        "fast": settings.fast_model,
        "synthesis": settings.synthesis_model,
        "embedding": settings.embedding_model,
    }}


class IngestState(str, Enum):
    """Lifecycle states for a background ingestion task."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IngestTask:
    """Durable, typed status for a single ingestion task.

    ``legacy_status`` reproduces the original stringly-typed contract
    ("running" / "completed:N" / "failed:msg") so existing clients keep
    working, while ``state``/``chunks``/``error``/timestamps are the new
    structured fields.
    """

    task_id: str
    state: IngestState = IngestState.RUNNING
    chunks: Optional[int] = None
    error: Optional[str] = None
    stage: Optional[str] = None          # live pipeline phase (resolving/fetching/…)
    detail: dict = field(default_factory=dict)  # stage-specific counts for the UI
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def mark_stage(self, event: dict) -> None:
        """Record a live pipeline phase from the ingest progress callback."""
        self.stage = event.get("stage")
        self.detail = {k: v for k, v in event.items() if k != "stage"}
        self.updated_at = time.time()

    @property
    def legacy_status(self) -> str:
        if self.state is IngestState.COMPLETED:
            return f"completed:{self.chunks}"
        if self.state is IngestState.FAILED:
            return f"failed:{self.error}"
        return self.state.value  # "running"

    def mark_completed(self, chunks: int) -> None:
        self.state = IngestState.COMPLETED
        self.chunks = chunks
        self.updated_at = time.time()

    def mark_failed(self, error: str) -> None:
        self.state = IngestState.FAILED
        self.error = error
        self.updated_at = time.time()

    def to_response(self) -> dict:
        """Backward-compatible JSON: keeps ``task_id`` + ``status`` (the legacy
        string) and adds the new typed fields alongside."""
        return {
            "task_id": self.task_id,
            "status": self.legacy_status,
            "state": self.state.value,
            "chunks": self.chunks,
            "error": self.error,
            "stage": self.stage,
            "detail": self.detail,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


# In-memory status tracker for ingestion tasks (single-worker POC).
# In a production app, use Redis/Celery for cross-process durability.
# Bounded: keeps memory from growing without limit over a long-lived process by
# evicting the oldest FINISHED tasks once over the cap (running tasks are never
# evicted, so an in-flight ingest's status is always retrievable).
_ingest_tasks: dict = {}
_ingest_lock = threading.Lock()
_MAX_INGEST_TASKS = 200


def _evict_ingest_tasks_locked() -> None:
    """Drop oldest finished tasks while over the cap. Caller holds the lock."""
    if len(_ingest_tasks) < _MAX_INGEST_TASKS:
        return
    finished = sorted(
        (t for t in _ingest_tasks.values() if t.state is not IngestState.RUNNING),
        key=lambda t: t.updated_at,
    )
    # Evict enough to leave headroom for new tasks.
    for task in finished:
        if len(_ingest_tasks) < _MAX_INGEST_TASKS:
            break
        _ingest_tasks.pop(task.task_id, None)


@app.post("/ingest", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """Trigger ingestion of an SEC filing. Returns immediately; status tracked via /ingest/status."""
    task_id = f"{request.ticker}-{request.document_type}-{request.year or 'latest'}"

    with _ingest_lock:
        existing = _ingest_tasks.get(task_id)
        if existing is not None and existing.state is IngestState.RUNNING:
            return {"status": "already_running", "task_id": task_id}
        _evict_ingest_tasks_locked()
        _ingest_tasks[task_id] = IngestTask(task_id=task_id)

    log_event("INFO", "ingest_started", task_id=task_id, ticker=request.ticker,
              document_type=request.document_type, year=request.year)
    background_tasks.add_task(_run_ingest, task_id, request)

    return {"status": "started", "task_id": task_id}


@app.get("/ingest/status/{task_id}")
async def get_ingest_status(task_id: str):
    task = _ingest_tasks.get(task_id)
    if task is None:
        return {"task_id": task_id, "status": "not_found", "state": "not_found",
                "chunks": None, "error": None}
    return task.to_response()


async def _run_ingest(task_id: str, request: IngestRequest):
    task = _ingest_tasks.get(task_id)
    try:
        logger.info(f"Starting background ingestion for {task_id}")
        # Forward pipeline-stage events onto the typed task so /ingest/status
        # reflects live progress (resolving → fetching → … → storing).
        on_progress = task.mark_stage if task is not None else None
        count = await asyncio.to_thread(
            ingest_filing,
            ticker=request.ticker,
            document_type=request.document_type,
            year=request.year,
            on_progress=on_progress,
        )
        if task is not None:
            task.mark_completed(count)
        log_event("INFO", "ingest_completed", task_id=task_id, chunks=count)
    except Exception as e:
        logger.exception(f"Background ingestion failed for {task_id}")
        if task is not None:
            task.mark_failed(str(e))
        log_event("ERROR", "ingest_failed", task_id=task_id, error=str(e))


@app.post("/retrieve", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def retrieve_chunks(request: QueryRequest):
    """Raw retrieval endpoint — returns top-k chunks with scores. Useful for frontend citation panel."""
    chunks = await asyncio.to_thread(
        retrieve,
        query=request.query,
        top_k=request.top_k,
        ticker=request.ticker,
        year=request.year,
        document_type=request.document_type,
    )
    return {"chunks": [c.model_dump() for c in chunks]}


@app.get("/filings")
async def list_filings():
    """List all ingested filings (distinct ticker/doc_type/year) with chunk counts."""
    def _aggregate():
        table = get_table()
        # Project only the 3 metadata columns so the heavy vector/text columns
        # never leave disk; single materialization instead of two full scans.
        # search().select() requires an explicit limit; use the row count.
        row_count = table.count_rows()
        df = (
            table.search()
            .select(["ticker", "document_type", "filing_year"])
            .limit(max(row_count, 1))
            .to_pandas()
        )
        return (
            df.groupby(["ticker", "document_type", "filing_year"])
            .size()
            .reset_index(name="chunks")
            .to_dict(orient="records")
        )

    try:
        counts = await asyncio.to_thread(_aggregate)
        return {"filings": counts}
    except Exception:
        logger.exception("Failed to list filings")
        raise HTTPException(status_code=500, detail="Failed to list filings")


@app.get("/insiders/{ticker}", dependencies=[Depends(enforce_rate_limit)])
async def insiders(ticker: str, limit: int = 12):
    """Recent insider (Form 4) buy/sell activity for a ticker. EDGAR-only — no
    LLM/key. Powers the sidebar insider panel and the agent's insider tool."""
    limit = max(1, min(limit, 30))
    try:
        activity = await asyncio.to_thread(get_insider_activity, ticker, limit)
        return activity.to_dict()
    except Exception:
        logger.exception("Failed to fetch insider activity")
        raise HTTPException(status_code=502, detail="Failed to fetch insider activity")


@app.get("/institutions/{fund}", dependencies=[Depends(enforce_rate_limit)])
async def institutions(fund: str, top: int = 25):
    """A fund's latest 13F top holdings (fund = its ticker/CIK, e.g. BRK-B)."""
    top = max(1, min(top, 100))
    try:
        holdings = await asyncio.to_thread(get_fund_holdings, fund, top)
        return holdings.to_dict()
    except Exception:
        logger.exception("Failed to fetch fund holdings")
        raise HTTPException(status_code=502, detail="Failed to fetch fund holdings")


@app.get("/smart-money/{ticker}")
async def smart_money(ticker: str):
    """Which TRACKED superinvestor funds (see backend/holdings/funds.json) hold
    this ticker, with Q/Q change. Reads the cached index — fast, no fetch. Run
    POST /smart-money/refresh to (re)build the index first."""
    try:
        ownership = await asyncio.to_thread(funds_holding_lookup, ticker)
        return ownership.to_dict()
    except Exception:
        logger.exception("Failed to read smart-money index")
        raise HTTPException(status_code=500, detail="Failed to read smart-money index")


@app.post("/smart-money/refresh", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def smart_money_refresh():
    """Rebuild the smart-money index: fetch each tracked fund's latest+prior 13F
    from EDGAR. Takes ~10-20s for the default roster; EDGAR-only (no LLM/key)."""
    try:
        result = await asyncio.to_thread(refresh_smart_money)
        return result
    except Exception:
        logger.exception("Smart-money refresh failed")
        raise HTTPException(status_code=502, detail="Smart-money refresh failed")


@app.post("/chat", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def chat(request: ChatRequest, http_request: Request):
    """
    Conversational endpoint. Returns a streaming SSE response.
    Each event is a JSON object: {"type": ..., "data": ...} where type is one of:
      status        — human-readable progress line (data: str)
      agent_step    — an autonomous action the agent took, e.g. auto-ingesting a
                      missing filing (data: {"kind": str, "label": str})
      chunk         — a synthesized answer token (data: str)
      verification  — critic-pass result (data: {"status": str, "issues": [str]})
      sources       — retrieved source metadata for the citation panel (data: list)
      error         — failure message (data: str)
      done          — end of stream (data: null)
    """
    return StreamingResponse(
        _chat_stream(request, http_request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _client_gone(http_request) -> bool:
    """Best-effort check for client disconnect.

    ``http_request`` may be a real Starlette Request or a lightweight stand-in
    in tests; tolerate a missing ``is_disconnected``.
    """
    is_disconnected = getattr(http_request, "is_disconnected", None)
    if is_disconnected is None:
        return False
    try:
        return await is_disconnected()
    except Exception:  # pragma: no cover - defensive
        return False


def _agent_model() -> str:
    """Model that drives the ReAct loop's reasoning (falls back to synthesis)."""
    return settings.agent_model or settings.synthesis_model


def _corpus_summary() -> str:
    """Compact, model-facing listing of what filings the corpus holds.

    Used by the ReAct ``list_corpus`` tool. Best-effort: returns a short message
    on any error rather than raising into the agent loop.
    """
    try:
        table = get_table()
        n = table.count_rows()
        if not n:
            return "The corpus is currently empty — ingest a filing first."
        df = (
            table.search().select(["ticker", "document_type", "filing_year"]).limit(n).to_pandas()
        )
        counts = (
            df.groupby(["ticker", "document_type", "filing_year"]).size().reset_index(name="n")
        )
        parts = [
            f"{r.ticker} {r.document_type} {int(r.filing_year)} ({int(r.n)} chunks)"
            for r in counts.itertuples()
        ]
        return "Corpus contains: " + "; ".join(parts)
    except Exception as e:  # noqa: BLE001
        return f"Could not read the corpus: {e}"


async def _react_gather(agent: ReactAgent, message: str, history, filters: dict, holder: dict):
    """Run the (sync) ReAct gather loop in a worker thread, yielding each
    agent-step event as it happens via a thread→event-loop queue bridge. The
    final GatherResult (or the raised error) is stashed in ``holder``."""
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def on_event(event: dict) -> None:
        loop.call_soon_threadsafe(q.put_nowait, event)

    def work() -> None:
        try:
            holder["result"] = agent.run(message, history, filters, on_event)
        except Exception as e:  # noqa: BLE001 — surfaced to the caller via holder
            holder["error"] = e
        finally:
            loop.call_soon_threadsafe(q.put_nowait, _DONE)

    task = loop.run_in_executor(None, work)
    while True:
        item = await q.get()
        if item is _DONE:
            break
        yield item
    await task


async def _chat_stream(request: ChatRequest, http_request=None) -> AsyncGenerator[str, None]:
    request_id = get_request_id()

    def sse(event_type: str, data) -> str:
        payload = json.dumps({"type": event_type, "data": data})
        return f"data: {payload}\n\n"

    try:
        # ── Step 1: Gather evidence ──────────────────────────────────────────
        # Two strategies (config-selected):
        #   * ReAct agent — a model-driven tool loop (search/ingest/list over
        #     multiple steps). The model writes its own search queries and
        #     decides when to fetch a missing filing.
        #   * Fixed pipeline (round 5) — condense → retrieve → optional one
        #     auto-ingest → re-retrieve. Simpler, fewer LLM calls.
        # Both produce ``chunks`` (a list of RetrievedChunk) and stream their own
        # status / agent_step events, then converge on the shared synthesis tail.
        if settings.enable_react_agent:
            yield sse("status", "Planning the analysis...")
            filters = {
                "ticker": request.ticker,
                "year": request.year,
                "document_type": request.document_type,
            }
            native = settings.agent_native_tools and supports_native_tools(_agent_model())
            agent = ReactAgent(
                generate_fn=generate,
                retrieve_fn=retrieve,
                ingest_fn=ingest_filing,
                list_corpus_fn=_corpus_summary,
                model=_agent_model(),
                max_steps=settings.agent_max_steps,
                native=native,
                insider_fn=get_insider_activity,
                fund_fn=get_fund_holdings,
                funds_holding_fn=funds_holding_lookup,
                financials_fn=_financials_tool,
                valuation_fn=_valuation_tool,
                thesis_fn=_thesis_tool,
            )
            holder: dict = {}
            async for ev in _react_gather(
                agent, request.message, request.conversation_history, filters, holder
            ):
                yield sse("agent_step", ev)
            if "error" in holder:
                raise holder["error"]
            result = holder.get("result")
            chunks = result.sources if result is not None else []
        else:
            # Fixed pipeline. condense_query degrades gracefully to the original
            # message; extract_filters returns {} on failure — retrieval is never
            # broken by a bad/absent key.
            yield sse("status", "Reading your question...")
            search_query = await asyncio.to_thread(
                condense_query, request.conversation_history, request.message
            )
            auto_filters = await asyncio.to_thread(extract_filters, search_query)
            eff_ticker = request.ticker or auto_filters.get("ticker")
            eff_year = request.year or auto_filters.get("year")
            eff_doc_type = request.document_type or auto_filters.get("document_type")

            yield sse("status", "Searching the filing corpus...")
            chunks = await asyncio.to_thread(
                retrieve, query=search_query, top_k=5,
                ticker=eff_ticker, year=eff_year, document_type=eff_doc_type,
            )

            # Corpus autonomy: fetch a missing filing on demand, then re-search.
            if settings.enable_auto_ingest:
                plan = plan_auto_ingest(eff_ticker, eff_doc_type, eff_year, chunks)
                if plan is not None:
                    yield sse("agent_step", {
                        "kind": "ingest",
                        "label": f"No {plan.label} in the corpus yet — fetching it from SEC EDGAR…",
                    })
                    try:
                        await asyncio.to_thread(
                            ingest_filing, ticker=plan.ticker,
                            document_type=plan.document_type, year=plan.year,
                        )
                        yield sse("agent_step", {
                            "kind": "retry_search",
                            "label": f"Ingested {plan.label}. Re-searching…",
                        })
                        chunks = await asyncio.to_thread(
                            retrieve, query=search_query, top_k=5,
                            ticker=eff_ticker, year=eff_year, document_type=eff_doc_type,
                        )
                    except Exception as e:  # noqa: BLE001 — surfaced as a step
                        logger.warning(f"Auto-ingest failed for {plan.label}: {e}")
                        yield sse("agent_step", {
                            "kind": "ingest_failed",
                            "label": f"Couldn't fetch {plan.label} from EDGAR ({e}).",
                        })

        if not chunks:
            yield sse("chunk", "I couldn't find relevant SEC filing data for your query, "
                               "and couldn't fetch a matching filing from EDGAR. Try a "
                               "different ticker or ingest a filing manually.")
            yield sse("done", None)
            return

        yield sse("status", f"Synthesizing {len(chunks)} retrieved SEC excerpts...")

        # Step 2: Build context for synthesis
        sources_context = _format_sources(chunks)
        history_context = _format_history(
            request.conversation_history, current_message=request.message
        )
        history_block = (
            f"CONVERSATION SO FAR (for resolving follow-up references):\n"
            f"{history_context}\n\n"
            if history_context
            else ""
        )
        full_prompt = (
            f"{_SYNTHESIS_SYSTEM_PROMPT}\n\n"
            f"{history_block}"
            f"SOURCE DOCUMENTS:\n{sources_context}\n\n"
            f"USER QUESTION: {request.message}"
        )

        # Step 3: Stream synthesis response token-by-token.
        # stream_generate is a sync generator; bridge it to async via a BOUNDED
        # queue so tokens are forwarded as they arrive without buffering without
        # limit. A cooperative threading.Event lets the producer stop calling the
        # (paid) LLM the moment the client disconnects or the generator is closed.
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SSE_QUEUE_MAXSIZE)
        stop_event = threading.Event()
        _DONE = object()
        # Accumulate streamed tokens so the post-synthesis critic pass can audit
        # the full answer against the sources.
        answer_parts: list[str] = []

        def _enqueue(item) -> None:
            # Runs on the event loop thread. If the consumer is slow and the
            # queue is full, drop the token rather than grow memory unbounded;
            # back-pressure is instead signalled to the producer via stop_event.
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

        def _schedule(item) -> None:
            # The consumer loop may already be closed if the request ended
            # abruptly; treat that as another stop signal rather than raising.
            try:
                loop.call_soon_threadsafe(_enqueue, item)
            except RuntimeError:
                stop_event.set()

        # Holds an exception raised inside the producer thread (e.g. a missing
        # API key or a provider error mid-stream). Without this, a failing
        # producer would silently end the stream and the user would see an
        # empty answer with no error.
        producer_error: list = []

        def _produce():
            try:
                for text in stream_generate(full_prompt, model=settings.synthesis_model):
                    if stop_event.is_set():
                        break
                    # If the queue is full the client isn't keeping up; pause
                    # briefly and re-check the stop flag instead of spinning.
                    while queue.full() and not stop_event.is_set():
                        time.sleep(0.01)
                    if stop_event.is_set():
                        break
                    _schedule(text)
            except Exception as e:  # noqa: BLE001 — surfaced to the client below
                producer_error.append(e)
            finally:
                _schedule(_DONE)

        producer = threading.Thread(target=_produce, daemon=True)
        producer.start()

        try:
            while True:
                # Wait for the next token, but wake periodically to poll for a
                # client disconnect even if the producer has gone quiet.
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=_DISCONNECT_POLL_INTERVAL
                    )
                except asyncio.TimeoutError:
                    if await _client_gone(http_request):
                        stop_event.set()
                        log_event("INFO", "chat_client_disconnected",
                                  request_id=request_id)
                        return
                    continue

                if item is _DONE:
                    break
                answer_parts.append(item)
                yield sse("chunk", item)

                if await _client_gone(http_request):
                    stop_event.set()
                    log_event("INFO", "chat_client_disconnected",
                              request_id=request_id)
                    return
        finally:
            # Covers normal completion, disconnect, and GeneratorExit (the
            # consumer closing us): always signal the producer to stop pumping
            # paid tokens.
            stop_event.set()

        # A synthesis failure (bad/missing API key, provider outage, model
        # retired) must reach the client as an explicit error, not as a
        # silently empty answer.
        if producer_error:
            e = producer_error[0]
            logger.error(f"Synthesis stream failed: {e}")
            log_event("ERROR", "chat_synthesis_error", request_id=request_id, error=str(e))
            yield sse("error", f"Synthesis failed: {e} (ref: {request_id})")
            yield sse("done", None)
            return

        # Step 4: Self-verification — audit the answer's claims against the
        # sources before the user trusts it. Non-blocking: an "unknown" result
        # (LLM/parse failure) is sent without withholding the answer.
        if settings.enable_self_verification:
            yield sse("status", "Verifying the answer against sources...")
            verification = await asyncio.to_thread(
                verify_answer, "".join(answer_parts), sources_context
            )
            yield sse("verification", verification.to_dict())

        # Step 5: Send source metadata for frontend citation panel
        sources_payload = [
            {
                "ticker": c.chunk.ticker,
                "year": c.chunk.filing_year,
                "quarter": c.chunk.filing_quarter,
                "section": c.chunk.sec_item_section,
                "chunk_type": c.chunk.chunk_type,
                "text_content": c.chunk.text_content,
                "raw_payload": c.chunk.raw_payload,
                "score": c.score,
            }
            for c in chunks
        ]
        yield sse("sources", sources_payload)
        yield sse("done", None)

    except Exception as e:
        logger.exception("Chat stream error")
        log_event("ERROR", "chat_stream_error", request_id=request_id, error=str(e))
        # SSE contract: error `data` is a plain string (the frontend renders it
        # directly). request_id is preserved in the server log above and echoed
        # via the X-Request-ID response header for correlation.
        yield sse("error", f"{e} (ref: {request_id})")
        yield sse("done", None)


def _format_history(
    history,
    max_turns: int = 6,
    max_chars: int = 1000,
    current_message: str = None,
) -> str:
    """Render prior conversation turns into a compact transcript for the prompt.

    Bounded by the last ``max_turns`` valid messages and ``max_chars`` per
    message. Malformed entries (non-dict, missing role/content, blank content)
    are skipped. If ``current_message`` is supplied and matches the final user
    turn, that trailing duplicate is dropped (the frontend appends the live
    message to history before sending).
    """
    cleaned = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        cleaned.append((role, content))

    if (
        current_message is not None
        and cleaned
        and cleaned[-1] == ("user", current_message.strip())
    ):
        cleaned.pop()

    if not cleaned:
        return ""

    lines = []
    for role, content in cleaned[-max_turns:]:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content[:max_chars]}")
    return "\n".join(lines)


# Max characters of a chunk's raw payload included in the synthesis prompt.
_SOURCE_PAYLOAD_LIMIT = 2000


def _truncate_payload(payload: str, chunk_type: str, limit: int = _SOURCE_PAYLOAD_LIMIT) -> str:
    """Truncate a source payload for the synthesis prompt.

    For table chunks, cut on a row boundary (the last ``</tr>`` within the
    limit) so the LLM never sees a table sliced mid-row — a mid-row cut can
    pair a label with the wrong number. Falls back to a plain character cut
    when no row boundary exists in range.
    """
    if len(payload) <= limit:
        return payload
    if chunk_type == "table":
        cut = payload.rfind("</tr>", 0, limit)
        if cut != -1:
            return payload[: cut + len("</tr>")]
    return payload[:limit]


def _format_sources(chunks) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {c.chunk.ticker} {c.chunk.document_type} {c.chunk.filing_year} "
            f"({c.chunk.filing_quarter}) — {c.chunk.sec_item_section}\n"
            f"{_truncate_payload(c.chunk.raw_payload, c.chunk.chunk_type)}"
        )
    return "\n\n---\n\n".join(parts)


