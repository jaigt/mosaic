# Mosaic — Backend Reference

> **Scope:** Python backend only (frontend: [`./FRONTEND_IMPLEMENTATION.md`](./FRONTEND_IMPLEMENTATION.md)).
> **Last updated:** 2026-06-15 (agentic core, ReAct, local embeddings, holdings trackers, rebrand).
>
> For the authoritative current state + invariants see
> [`../PROJECT_STATUS_AND_ROADMAP.md`](../PROJECT_STATUS_AND_ROADMAP.md); for the
> live backlog see [`../TODO.md`](../TODO.md).

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
│   │   ├── filters.py            # Allowlist validation + SQL-quote escaping (+ ISO-date)
│   │   ├── retriever.py          # Pre-filtered vector search + hybrid + diversify
│   │   ├── hybrid.py             # Reciprocal Rank Fusion (vector + BM25-lite lexical)
│   │   ├── rerank.py             # MMR / Jaccard diversification
│   │   └── reformulate.py        # History-aware condense-question query rewriting
│   ├── agent/                    # AGENTIC CORE
│   │   ├── planner.py            # plan_auto_ingest (corpus autonomy) + verify_answer (critic)
│   │   └── react.py              # multi-tool ReAct loop (text + native Gemini function-calling)
│   ├── holdings/                 # EDGAR-only trackers (no LLM/key)
│   │   ├── insiders.py           # Form 4 insider buy/sell, per ticker
│   │   ├── institutions.py       # 13F fund holdings, per fund
│   │   ├── superinvestors.py     # smart-money: which curated funds hold ticker X (+ Q/Q change)
│   │   ├── models.py             # InsiderActivity / FundHoldings / TickerOwnership
│   │   └── funds.json            # curated superinvestor CIK registry (editable)
│   ├── eval/                     # offline retrieval eval harness (hit@k / MRR)
│   ├── tests/                    # pytest suite (247 passing)
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
| LLM routing | `llm.py` abstraction | Swap providers via `.env` by model-name prefix; native function-calling for Gemini |
| Embeddings | **`local-bge-large`** (fastembed/ONNX, default) | CPU, $0, no key/quota; 1024-dim. Hosted (`gemini-embedding-001` 3072-dim, `text-embedding-3-*`) still selectable |
| Agent | ReAct loop (`agent/`) | Model-driven tools: search / auto-ingest / list / insider / 13F / smart-money, then a self-verification critic |
| API layer | FastAPI + SSE streaming | Token-by-token streaming via a thread→asyncio.Queue bridge |

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

### `GET /insiders/{ticker}`, `GET /institutions/{fund}`, `GET /smart-money/{ticker}`, `POST /smart-money/refresh`
Holdings trackers (EDGAR-only, no LLM/key). Insider Form 4 activity per ticker; a
fund's 13F top holdings per fund; which curated superinvestors hold a ticker (+
Q/Q change, served from a cached index auto-refreshed on startup); and a manual
index rebuild. (Manual filing ingestion still has `POST /ingest` +
`/ingest/status/{id}` as a programmatic path, but there is **no manual-ingest UI**
— the agent auto-ingests on demand.)

### `POST /chat`
Conversational endpoint. Returns a **streaming SSE response**, driven by the
**ReAct agent** by default (`enable_react_agent`): the model gathers evidence with
tools (search / auto-ingest / insider / 13F / smart-money), then synthesis streams
with citations + optional `<chart>`, then a self-verification critic runs. Optional
explicit filters scope the analysis; multi-turn aware (history condenses follow-ups
+ feeds the synthesis prompt).

SSE events are JSON objects `{"type": ..., "data": ...}` where type ∈
`status | agent_step | chunk | verification | sources | error | done`.
(`agent_step` = an autonomous action like auto-ingesting; `verification` = the
critic result.)

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

Routing is by **model-name prefix** (`claude-`/`gemini-`/`gpt-`/`o*`; `local-*` for
embeddings). Models verified live 2026-06-15 — pin **stable GA** names, not
`*-preview` (a prior preview pin caused silent 404s).

| Role | Default | Alternatives |
|---|---|---|
| Fast model (table summaries, filters, verification) | `gemini-2.5-flash-lite` | `claude-haiku-4-5`, `gpt-*-mini` |
| Synthesis / agent reasoning | `gemini-2.5-flash` | `claude-sonnet-4-6`, `gpt-*` |
| Embedding | **`local-bge-large`** (1024-dim, offline) | `gemini-embedding-001` (3072), `text-embedding-3-large` (3072) |

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
    period_of_report: str | None  # raw period-end date (YYYY-MM-DD); unambiguous vs the calendar filing_quarter
```

> Insider/13F tool results reach synthesis as **citable synthetic sources**
> (duck-typed, not `DocumentChunk` — see `react.py`), so the agent can cite their
> figures alongside filing excerpts.
