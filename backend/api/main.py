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
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.api.security import enforce_rate_limit, require_api_key
from backend.config import settings
from backend.models.schemas import ChatRequest, IngestRequest, QueryRequest
from backend.pipeline.ingest import ingest_filing
from backend.pipeline.llm import stream_generate
from backend.pipeline.store import get_table
from backend.retrieval.retriever import retrieve

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Value Investing RAG API", version="0.1.0")

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
- Use the following format for charts:
<chart>
{
  "title": "Comparison of Revenue (Billions)",
  "data": [
    {"name": "2022", "value": 117.1},
    {"name": "2023", "value": 125.4},
    {"name": "2024", "value": 130.2}
  ]
}
</chart>
- Always continue with your textual analysis AFTER the chart tag if needed.
"""


@app.get("/health")
def health():
    return {"status": "ok", "models": {
        "fast": settings.fast_model,
        "synthesis": settings.synthesis_model,
        "embedding": settings.embedding_model,
    }}


# Simple in-memory status tracker for ingestion tasks
# In a production app, use Redis/Celery.
_ingest_tasks = {}

@app.post("/ingest", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """Trigger ingestion of an SEC filing. Returns immediately; status tracked via /ingest/status."""
    task_id = f"{request.ticker}-{request.document_type}-{request.year or 'latest'}"
    
    if _ingest_tasks.get(task_id) == "running":
        return {"status": "already_running", "task_id": task_id}

    _ingest_tasks[task_id] = "running"
    background_tasks.add_task(_run_ingest, task_id, request)
    
    return {"status": "started", "task_id": task_id}


@app.get("/ingest/status/{task_id}")
async def get_ingest_status(task_id: str):
    status = _ingest_tasks.get(task_id, "not_found")
    return {"task_id": task_id, "status": status}


async def _run_ingest(task_id: str, request: IngestRequest):
    try:
        logger.info(f"Starting background ingestion for {task_id}")
        count = await asyncio.to_thread(
            ingest_filing,
            ticker=request.ticker,
            document_type=request.document_type,
            year=request.year,
        )
        _ingest_tasks[task_id] = f"completed:{count}"
        logger.info(f"Background ingestion completed for {task_id}: {count} chunks")
    except Exception as e:
        logger.exception(f"Background ingestion failed for {task_id}")
        _ingest_tasks[task_id] = f"failed:{str(e)}"


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


@app.post("/chat", dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])
async def chat(request: ChatRequest):
    """
    Conversational endpoint. Returns a streaming SSE response.
    Each event is a JSON object: {"type": "status"|"chunk"|"sources"|"done", "data": ...}
    """
    return StreamingResponse(
        _chat_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _chat_stream(request: ChatRequest) -> AsyncGenerator[str, None]:
    def sse(event_type: str, data) -> str:
        payload = json.dumps({"type": event_type, "data": data})
        return f"data: {payload}\n\n"

    try:
        # Step 1: Retrieval
        yield sse("status", "Extracting filters from query...")
        chunks = await asyncio.to_thread(
            retrieve, 
            query=request.message, 
            top_k=5,
            ticker=request.ticker,
            year=request.year,
            document_type=request.document_type
        )

        if not chunks:
            yield sse("chunk", "I couldn't find relevant SEC filing data for your query. Try ingesting a filing first.")
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

        # Step 3: Stream synthesis response token-by-token
        # stream_generate is a sync generator; bridge it to async via a queue
        # so tokens are forwarded as they arrive rather than buffered.
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _DONE = object()

        def _produce():
            try:
                for text in stream_generate(full_prompt, model=settings.synthesis_model):
                    loop.call_soon_threadsafe(queue.put_nowait, text)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _DONE)

        threading.Thread(target=_produce, daemon=True).start()

        while True:
            item = await queue.get()
            if item is _DONE:
                break
            yield sse("chunk", item)

        # Step 4: Send source metadata for frontend citation panel
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
        yield sse("error", str(e))
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


def _format_sources(chunks) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {c.chunk.ticker} {c.chunk.document_type} {c.chunk.filing_year} "
            f"({c.chunk.filing_quarter}) — {c.chunk.sec_item_section}\n"
            f"{c.chunk.raw_payload[:2000]}"
        )
    return "\n\n---\n\n".join(parts)


