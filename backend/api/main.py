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
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.models.schemas import ChatRequest, IngestRequest, QueryRequest
from backend.pipeline.ingest import ingest_filing
from backend.pipeline.llm import stream_generate
from backend.retrieval.retriever import retrieve

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Value Investing RAG API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

_SYNTHESIS_SYSTEM_PROMPT = """\
You are an expert value investing analyst with deep knowledge of SEC filings. \
You are given retrieved excerpts from real SEC filings to answer the user's question.

Rules:
- Base your answer strictly on the provided SOURCE DOCUMENTS.
- Always cite which filing (ticker, year, section) each claim comes from.
- If the sources do not contain enough information to answer fully, say so explicitly.
- Be concise and precise. Avoid filler text.
"""


@app.get("/health")
def health():
    return {"status": "ok", "models": {
        "fast": settings.fast_model,
        "synthesis": settings.synthesis_model,
        "embedding": settings.embedding_model,
    }}


@app.post("/ingest")
async def ingest(request: IngestRequest):
    """Trigger ingestion of an SEC filing. Runs synchronously (can take minutes)."""
    try:
        count = await asyncio.to_thread(
            ingest_filing,
            ticker=request.ticker,
            document_type=request.document_type,
            year=request.year,
        )
        return {"status": "ok", "chunks_stored": count, "ticker": request.ticker}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Ingestion failed for {request.ticker}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/retrieve")
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


@app.post("/chat")
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
        chunks = await asyncio.to_thread(retrieve, query=request.message, top_k=5)

        if not chunks:
            yield sse("chunk", "I couldn't find relevant SEC filing data for your query. Try ingesting a filing first.")
            yield sse("done", None)
            return

        yield sse("status", f"Synthesizing {len(chunks)} retrieved SEC excerpts...")

        # Step 2: Build context for synthesis
        sources_context = _format_sources(chunks)
        full_prompt = (
            f"{_SYNTHESIS_SYSTEM_PROMPT}\n\n"
            f"SOURCE DOCUMENTS:\n{sources_context}\n\n"
            f"USER QUESTION: {request.message}"
        )

        # Step 3: Stream synthesis response (Claude or Gemini per SYNTHESIS_MODEL config)
        for text in await asyncio.to_thread(lambda: list(stream_generate(full_prompt, model=settings.synthesis_model))):
            yield sse("chunk", text)

        # Step 4: Send source metadata for frontend citation panel
        sources_payload = [
            {
                "ticker": c.chunk.ticker,
                "year": c.chunk.filing_year,
                "quarter": c.chunk.filing_quarter,
                "section": c.chunk.sec_item_section,
                "chunk_type": c.chunk.chunk_type,
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


def _format_sources(chunks) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {c.chunk.ticker} {c.chunk.document_type} {c.chunk.filing_year} "
            f"({c.chunk.filing_quarter}) — {c.chunk.sec_item_section}\n"
            f"{c.chunk.raw_payload[:2000]}"
        )
    return "\n\n---\n\n".join(parts)


