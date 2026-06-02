# Value Investing RAG — Backend Reference

> **Scope:** This document covers the Python backend only. Frontend/UI is handled separately (see [`../blueprints/ValueInvestingUI.md`](../blueprints/ValueInvestingUI.md) and [`./FRONTEND_IMPLEMENTATION.md`](./FRONTEND_IMPLEMENTATION.md)).
> **Last updated:** 2026-06-02
>
> For current state / open work, see [`../TODO.md`](../TODO.md) and [`../PROJECT_STATUS_AND_ROADMAP.md`](../PROJECT_STATUS_AND_ROADMAP.md).

---

## Table of Contents
1. [Project Structure](#1-project-structure)
2. [Tech Stack & Decisions](#2-tech-stack--decisions)
3. [Setup & Running](#3-setup--running)
4. [Architecture Overview](#4-architecture-overview)
5. [Module Reference](#5-module-reference)
6. [API Endpoints](#6-api-endpoints)
7. [Multi-Provider LLM System](#7-multi-provider-llm-system)
8. [Data Model](#8-data-model)
9. [Configuration Reference](#9-configuration-reference)
10. [Upgrade Path (POC → Production)](#10-upgrade-path-poc--production)

---

## 1. Project Structure

```
valueinvesting/
├── backend/
│   ├── api/
│   │   ├── main.py               # FastAPI app — all HTTP endpoints, SSE chat
│   │   ├── security.py           # Optional API-key auth + per-IP rate limiting
│   │   └── observability.py      # X-Request-ID middleware + structured logging
│   ├── ingestion/
│   │   ├── edgar_fetcher.py      # Fetches SEC filings via edgartools
│   │   ├── parser.py             # Parses narrative HTML → elements by section (path A)
│   │   └── xbrl_parser.py        # Structured XBRL financial statements (path B)
│   ├── models/
│   │   └── schemas.py            # Pydantic models (DocumentChunk, API requests)
│   ├── pipeline/
│   │   ├── embedder.py           # Provider-agnostic text embedding
│   │   ├── ingest.py             # Full ingestion orchestrator (parallel table summaries)
│   │   ├── llm.py                # Provider-agnostic LLM calls (generate + stream)
│   │   ├── store.py              # LanceDB connection cache, upsert, index
│   │   ├── table_summarizer.py   # Two-pass table strategy (raw → semantic summary)
│   │   └── ratelimit.py          # Token bucket for ingestion-side LLM throttling
│   ├── retrieval/
│   │   ├── query_parser.py       # Extracts metadata filters from natural language
│   │   ├── filters.py            # Allowlist validation + SQL-quote escaping (injection-safe)
│   │   ├── retriever.py          # Pre-filtered vector search + hybrid + diversify
│   │   ├── hybrid.py             # Reciprocal Rank Fusion (vector + BM25-lite lexical)
│   │   ├── rerank.py             # MMR / Jaccard diversification
│   │   └── reformulate.py        # History-aware condense-question query rewriting
│   ├── tests/                    # pytest suite (99 passing)
│   ├── config.py                 # Pydantic-settings (loads from .env)
│   └── requirements.txt
├── data/
│   └── lancedb/                  # Local vector DB (git-ignored)
├── .env                          # Your secrets (git-ignored)
├── .env.example                  # Template — copy to .env and fill in
└── docs/                         # All documentation (this file lives in docs/reference/)
```

---

## 2. Tech Stack & Decisions

### Core choices

| Component | Choice | Why |
|---|---|---|
| Language | Python | Ecosystem fit for ML/finance |
| Vector DB | LanceDB (local) | Free, runs on disk, supports SQL-like metadata pre-filtering |
| SEC data | `edgartools` | Clean Python API over SEC EDGAR |
| HTML parsing | `unstructured` | Local, free, layout-aware (extracts Tables vs NarrativeText) |
| LLM routing | `llm.py` abstraction | Swap providers via `.env` without touching code |
| Embeddings | `gemini-embedding-001` (Google) | Free tier, 3072-dim, replaces retired `text-embedding-004` |
| API layer | FastAPI + SSE streaming | Token-by-token streaming to the frontend via a thread→asyncio.Queue bridge |

---

## 3. Setup & Running

### First-time setup

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp .env.example .env
```

### Running the API server

```bash
uvicorn backend.api.main:app --reload
```

---

## 4. Architecture Overview

### Ingestion pipeline (Asynchronous)
The ingestion process is decoupled from the HTTP request using FastAPI's `BackgroundTasks`.
1. **Trigger:** `POST /ingest` starts a task and returns a `task_id`.
2. **Monitor:** `GET /ingest/status/{task_id}` allows the frontend to poll for completion.
3. **Execution:** The backend fetches, parses, summarizes, embeds, and stores the filing chunks.

---

## 6. API Endpoints

> **Auth & rate limiting:** `/ingest`, `/retrieve`, and `/chat` are guarded by
> `require_api_key` (header `X-API-Key`) and `enforce_rate_limit` (per-IP token
> bucket). Both are **no-ops by default** — auth is enforced only when
> `settings.api_key` is set, and rate limiting only when `rate_limit_per_minute > 0`.
> All responses carry an `X-Request-ID` header for log correlation.

### `GET /health`
Returns server status and active model config.

### `POST /ingest`
Triggers ingestion of an SEC filing. Returns immediately and runs in the background.

**Request:**
```json
{ "ticker": "AAPL", "document_type": "10-K", "year": 2024 }
```

**Response:**
```json
{ "status": "started", "task_id": "AAPL-10-K-2024" }
```

### `GET /ingest/status/{task_id}`
Returns the status of a background ingestion task.

**Response:**
```json
{ "task_id": "...", "status": "running", "state": "running",
  "chunks": null, "error": null, "started_at": 0, "updated_at": 0 }
// Backward-compatible: `status` is the legacy string
// ("running" | "completed:CHUNK_COUNT" | "failed:ERROR_MSG" | "not_found").
// `state`/`chunks`/`error`/timestamps are the newer typed fields.
```

### `POST /retrieve`
Raw retrieval — returns top-k chunks with similarity scores.

### `GET /filings`
Lists all ingested filings with chunk counts.

### `POST /chat`
Conversational endpoint. Returns a **streaming SSE response**. Supports optional
explicit filters to scope the analysis, and is **multi-turn aware**:
`conversation_history` is used both to condense follow-ups into standalone search
queries (retrieval) and to give the synthesis model prior context.

SSE events are JSON objects `{"type": "status"|"chunk"|"sources"|"done"|"error", "data": ...}`.

**Request:**
```json
{
  "message": "What were capital expenditures in 2024?",
  "conversation_history": [],
  "ticker": "AAPL",
  "year": 2024,
  "document_type": "10-K"
}
```

---

## 7. Multi-Provider LLM System

Supported model examples:

| Role | Free (POC default) | Paid alternatives |
|---|---|---|
| Fast model | `gemini-3.1-flash-lite-preview` | `claude-haiku-4-5-20251001`, `gpt-4o-mini` |
| Synthesis | `gemini-2.5-flash` | `claude-sonnet-4-6`, `gpt-4o` |
| Embedding | `gemini-embedding-001` (3072-dim) | `text-embedding-3-small`, `text-embedding-3-large` |

---

## 8. Data Model

Every chunk stored in LanceDB conforms to `DocumentChunk`:

```python
class DocumentChunk(BaseModel):
    chunk_id: str           # "{ticker}_{doc_type}_{year}_{quarter}_{index:05d}"
    ticker: str             # "AAPL"
    cik: str                # SEC CIK number
    document_type: str      # "10-K" | "10-Q" | "8-K"
    filing_year: int        # 2024
    filing_quarter: str     # "Q1" | "Q2" | "Q3" | "Q4" | "FY"
    sec_item_section: str   # "Item 7: MD&A"
    chunk_type: str         # "text" | "table"
    text_content: str       # What gets embedded (narrative text OR table summary)
    raw_payload: str        # What gets shown to LLM + user (original text or HTML)
```
