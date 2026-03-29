# Value Investing RAG — Backend Reference

> **Scope:** This document covers the Python backend only. Frontend/UI is handled separately (see `ValueInvestingUI.md`).
> **Last updated:** 2026-03-29

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
│   │   └── main.py               # FastAPI app — all HTTP endpoints
│   ├── ingestion/
│   │   ├── edgar_fetcher.py      # Fetches SEC filings via edgartools
│   │   └── parser.py             # Parses HTML → structured elements by section
│   ├── models/
│   │   └── schemas.py            # Pydantic models (DocumentChunk, API requests)
│   ├── pipeline/
│   │   ├── embedder.py           # Provider-agnostic text embedding
│   │   ├── ingest.py             # Full ingestion pipeline orchestrator
│   │   ├── llm.py                # Provider-agnostic LLM calls (generate + stream)
│   │   ├── store.py              # LanceDB upsert and table management
│   │   └── table_summarizer.py   # Two-pass table strategy (raw → semantic summary)
│   ├── retrieval/
│   │   ├── query_parser.py       # Extracts metadata filters from natural language
│   │   └── retriever.py          # Pre-filtered LanceDB vector search
│   ├── config.py                 # Pydantic-settings (loads from .env)
│   └── requirements.txt
├── data/
│   └── lancedb/                  # Local vector DB (git-ignored)
├── .env                          # Your secrets (git-ignored)
├── .env.example                  # Template — copy to .env and fill in
├── BACKEND.md                    # This file
├── ValueInvestingRAG.md          # Original architecture blueprint
└── ValueInvestingUI.md           # Frontend blueprint (Gemini's scope)
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
| Embeddings | `text-embedding-004` (Google) | Free tier, 768-dim, strong retrieval quality |
| API layer | FastAPI + SSE streaming | Matches frontend's Vercel AI SDK streaming expectations |

### POC cost decisions
- **All defaults are free-tier.** Google AI Studio offers free access to Gemini 2.0 Flash and Gemini 2.5 Pro.
- `FAST_MODEL` defaults to `gemini-2.0-flash` (free, fast, used for high-volume calls).
- `SYNTHESIS_MODEL` defaults to `gemini-2.5-pro-preview-03-25` (free, used for final user-facing answers).
- `EMBEDDING_MODEL` defaults to `text-embedding-004` (free via Google AI Studio).
- Upgrade paths are noted in [Section 10](#10-upgrade-path-poc--production).

### What was ruled out
- **LlamaParse** — requires paid API key; Unstructured.io handles the same job locally for free.
- **Cloud vector DBs** (Pinecone, Weaviate) — overkill for a local POC; LanceDB is sufficient and free.
- **Anthropic embeddings** — Anthropic has no embedding API; Google or OpenAI required.

---

## 3. Setup & Running

### First-time setup

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — at minimum set GOOGLE_API_KEY and SEC_USER_AGENT
```

### .env minimum config (free-tier)

```env
GOOGLE_API_KEY=your_key_from_aistudio.google.com
SEC_USER_AGENT="Your Name your@email.com"
```

### Running the API server

```bash
# From the project root
uvicorn backend.api.main:app --reload

# Server starts at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### Ingest a filing (example)

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "document_type": "10-K"}'
```

### Query (example)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What were Apple'\''s capital expenditures in 2024?"}'
```

---

## 4. Architecture Overview

The pipeline has two phases: **ingestion** (run once per filing) and **retrieval** (run on every user query).

### Ingestion pipeline

```
EDGAR (SEC)
    │
    ▼
edgar_fetcher.py       — fetch raw HTML, extract filing metadata
    │
    ▼
parser.py              — partition HTML into elements (Title, NarrativeText, Table)
                         track section headers (Item 1A, Item 7: MD&A, etc.)
    │
    ├── text elements ──────────────────────────────┐
    │                                               │
    └── table elements → table_summarizer.py        │
                         (Fast LLM: raw HTML        │
                          → semantic summary)        │
                                                    ▼
                                             embedder.py
                                             (text_content → vector)
                                                    │
                                                    ▼
                                             store.py → LanceDB
```

### Retrieval pipeline (per user query)

```
User query
    │
    ▼
query_parser.py        — Fast LLM extracts: ticker, year, doc_type from query
    │
    ▼
retriever.py           — Pre-filter LanceDB by metadata (ticker/year/doc_type)
                         then vector search on filtered subset
    │
    ▼
api/main.py            — Format retrieved chunks as source context
    │
    ▼
llm.py (stream)        — Synthesis LLM generates final answer, citing sources
    │
    ▼
SSE stream → frontend  — chunks: text tokens | sources: citation metadata | done
```

### The two-pass table strategy
SEC filings contain dense financial tables that embed poorly as raw HTML. The strategy:
1. **Summarize:** Send raw table to `FAST_MODEL` → get a semantic natural-language summary.
2. **Embed the summary** in `text_content` (what gets vectorized and searched).
3. **Store raw HTML** in `raw_payload` (what gets sent to the synthesis LLM and displayed in the citation panel).

This means vector search finds tables by *meaning*, while the final answer is grounded in the *actual numbers*.

---

## 5. Module Reference

### `backend/config.py`
Loads all settings from `.env` via `pydantic-settings`. Import `settings` anywhere to access config.

### `backend/models/schemas.py`
All Pydantic models:
- `DocumentChunk` — the core unit stored in LanceDB (see [Section 8](#8-data-model))
- `IngestRequest` — `POST /ingest` body: `ticker`, `document_type`, optional `year`
- `QueryRequest` — `POST /retrieve` body: `query`, optional filters, `top_k`
- `ChatRequest` — `POST /chat` body: `message`, `conversation_history`
- `RetrievedChunk` — a `DocumentChunk` + `score` float returned from retrieval

### `backend/ingestion/edgar_fetcher.py`
- `get_filing_html(ticker, document_type, year)` → `(html_str, metadata_dict)`
- Enforces a 150ms delay between requests to respect SEC rate limits (10 req/s max).
- `SEC_USER_AGENT` must be a real name + email per SEC policy.

### `backend/ingestion/parser.py`
- `parse_filing_html(html_str)` → `ParsedDocument`
- Uses `unstructured` to partition HTML into typed elements.
- Tracks section headers via regex (`Item \d+[a-z]?`) and tags every element with its parent section.
- Returns `ParsedDocument.elements` (flat list) and `ParsedDocument.section_map` (grouped by section).

### `backend/pipeline/llm.py`
- `generate(prompt, model)` → `str` — non-streaming, used for fast/cheap calls.
- `stream_generate(prompt, model)` → `Generator[str]` — streaming, used for synthesis.
- Routes to Anthropic, Google, or OpenAI based on model name prefix (see [Section 7](#7-multi-provider-llm-system)).

### `backend/pipeline/embedder.py`
- `embed_texts(texts)` → `list[list[float]]` — batched document embedding.
- `embed_query(text)` → `list[float]` — single query embedding (different task type).
- Routes to Google or OpenAI based on `EMBEDDING_MODEL` name.
- `EMBEDDING_DIM` is set at import time based on the configured model.

### `backend/pipeline/table_summarizer.py`
- `summarize_table(table_content, ticker, document_type)` → `str`
- Calls `llm.generate()` with `FAST_MODEL`.
- Retries 3× with exponential backoff via `tenacity`.
- Truncates tables to 8000 chars to avoid token overflow on large filings.

### `backend/pipeline/store.py`
- `get_table()` — connects to (or creates) the LanceDB `sec_chunks` table.
- `upsert_chunks(chunks, vectors)` — idempotent: deletes existing chunks for same filing before inserting.
- `generate_chunk_id(ticker, doc_type, year, quarter, index)` — deterministic ID for deduplication.

### `backend/pipeline/ingest.py`
- `ingest_filing(ticker, document_type, year)` → `int` (chunks stored)
- Orchestrates the full ingestion pipeline end-to-end. This is the only function the API calls.

### `backend/retrieval/query_parser.py`
- `extract_filters(query)` → `dict` with any of: `ticker`, `year`, `document_type`, `section`
- Uses `FAST_MODEL`. Fails gracefully — returns `{}` if parsing fails, so search still proceeds unfiltered.

### `backend/retrieval/retriever.py`
- `retrieve(query, top_k, ticker, year, document_type)` → `list[RetrievedChunk]`
- Explicit overrides take precedence over LLM-extracted filters.
- Applies a SQL `WHERE` clause to LanceDB before vector search — critical for precision on a multi-company, multi-year corpus.

### `backend/api/main.py`
FastAPI app. See [Section 6](#6-api-endpoints) for full endpoint docs.

---

## 6. API Endpoints

All endpoints are defined in `backend/api/main.py`.

### `GET /health`
Returns server status and active model config.
```json
{
  "status": "ok",
  "models": {
    "fast": "gemini-2.0-flash",
    "synthesis": "gemini-2.5-pro-preview-03-25",
    "embedding": "text-embedding-004"
  }
}
```

### `POST /ingest`
Triggers ingestion of an SEC filing. Runs synchronously (can take 1-5 minutes for a full 10-K).

**Request:**
```json
{ "ticker": "AAPL", "document_type": "10-K", "year": 2024 }
```
`year` is optional — omit for the most recent filing.

**Response:**
```json
{ "status": "ok", "chunks_stored": 312, "ticker": "AAPL" }
```

### `POST /retrieve`
Raw retrieval — returns top-k chunks with similarity scores. Useful for the frontend citation panel and debugging retrieval quality.

**Request:**
```json
{ "query": "Apple capital expenditures", "ticker": "AAPL", "top_k": 5 }
```

**Response:**
```json
{
  "chunks": [
    {
      "chunk": { "ticker": "AAPL", "filing_year": 2024, "sec_item_section": "Item 7: MD&A", ... },
      "score": 0.23
    }
  ]
}
```

### `POST /chat`
Conversational endpoint. Returns a **streaming SSE response**.

**Request:**
```json
{
  "message": "What were Apple's capital expenditures in 2024?",
  "conversation_history": []
}
```

**SSE event stream format** (each event is `data: <json>\n\n`):
```
data: {"type": "status", "data": "Extracting filters from query..."}
data: {"type": "status", "data": "Synthesizing 4 retrieved SEC excerpts..."}
data: {"type": "chunk",  "data": "Apple reported capital expenditures of..."}
data: {"type": "chunk",  "data": " $11.5 billion in fiscal year 2024..."}
data: {"type": "sources","data": [{"ticker": "AAPL", "year": 2024, "section": "Item 7: MD&A", "raw_payload": "...", ...}]}
data: {"type": "done",   "data": null}
```

Event types:
- `status` — progress update for the "thought process" UI indicator
- `chunk` — incremental text token from the synthesis LLM
- `sources` — array of citation objects (raw filing excerpts) for the document viewer panel
- `done` — stream complete
- `error` — something went wrong

---

## 7. Multi-Provider LLM System

All LLM calls route through `backend/pipeline/llm.py`. Provider is determined purely by model name prefix — no other configuration needed.

### Routing rules

| Model prefix | Provider | Required key |
|---|---|---|
| `claude-*` | Anthropic | `ANTHROPIC_API_KEY` |
| `gemini-*` | Google | `GOOGLE_API_KEY` |
| `gpt-*`, `o1`, `o3`, `o4` | OpenAI | `OPENAI_API_KEY` |

### Supported model examples

| Role | Free (POC default) | Paid alternatives |
|---|---|---|
| Fast model | `gemini-2.0-flash` | `claude-haiku-4-5-20251001`, `gpt-4o-mini` |
| Synthesis | `gemini-2.5-pro-preview-03-25` | `claude-sonnet-4-6`, `claude-opus-4-6`, `gpt-4o` |
| Embedding | `text-embedding-004` | `text-embedding-3-small`, `text-embedding-3-large` |

> **Note on synthesis quality:** Claude Sonnet/Opus tends to be more precise for financial citation tasks — stricter about not hallucinating numbers and better at following the "cite your source" instruction. Recommended for production. Gemini 2.5 Pro's advantage is a 1M token context window, which is overkill when retrieving 5 chunks but useful if you ever pass full documents.

### Switching providers (zero code changes)
```env
# Switch to Claude for synthesis:
SYNTHESIS_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# Switch fast model to Claude Haiku:
FAST_MODEL=claude-haiku-4-5-20251001

# Switch embeddings to OpenAI:
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```

> **Important:** If you change `EMBEDDING_MODEL` after ingesting data, you must re-ingest everything. Vectors from different embedding models are not comparable.

### Adding a new provider
1. Add detection logic to `_provider()` in `llm.py`.
2. Implement `_generate_<provider>()` and `_stream_<provider>()`.
3. Add the API key to `config.py` and `.env.example`.

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

The key distinction: `text_content` is optimized for semantic search; `raw_payload` is the ground truth. For tables, these are different (summary vs. raw HTML). For text, they are the same.

LanceDB table name: `sec_chunks`. Stored at `LANCEDB_PATH` (default: `./data/lancedb`).

---

## 9. Configuration Reference

Full `.env` reference:

```env
# ── Required ──────────────────────────────────────────────
GOOGLE_API_KEY=            # Google AI Studio key (embeddings + Gemini models)
SEC_USER_AGENT=            # "Your Name your@email.com" (SEC EDGAR requirement)

# ── Optional (only if using that provider) ────────────────
ANTHROPIC_API_KEY=         # claude-* models
OPENAI_API_KEY=            # gpt-* / o1 / o3 / o4 models

# ── Model config ──────────────────────────────────────────
FAST_MODEL=gemini-2.0-flash
SYNTHESIS_MODEL=gemini-2.5-pro-preview-03-25
EMBEDDING_MODEL=text-embedding-004

# ── Storage ───────────────────────────────────────────────
LANCEDB_PATH=./data/lancedb
```

---

## 10. Upgrade Path (POC → Production)

Decisions made for the POC that should be revisited before any public deployment:

| Area | POC state | Production recommendation |
|---|---|---|
| **Python version** | 3.9.6 (system) | Upgrade to 3.11+ (Google SDKs warn about 3.9 EOL) |
| **Synthesis model** | Gemini 2.5 Pro (free) | Claude Sonnet 4.6 for better citation precision |
| **CORS** | `allow_origins=["*"]` | Lock down to your frontend domain |
| **Ingest endpoint** | Synchronous, blocks request | Move to a background task queue (Celery / ARQ) |
| **LanceDB** | Local disk | Still valid at scale; or migrate to LanceDB Cloud |
| **SEC rate limiting** | Simple 150ms sleep | Add proper retry + jitter for concurrent ingestion |
| **Auth** | None | Add API key or OAuth before any public exposure |
| **Logging** | `basicConfig(INFO)` | Structured logging (structlog) + observability |
