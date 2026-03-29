# Value Investing RAG

A local, multi-provider RAG pipeline for querying SEC filings (10-Ks, 10-Qs) with LLM-powered analysis.

> **Status (2026-03-29):** POC fully functional end-to-end. Backend and frontend integrated with live SSE streaming. AAPL 10-Q successfully ingested and queried. Bug fixes applied to streaming, ingest modal, sidebar polling, table layout, and split-pane resizing. See [Session Log](#session-log-2026-03-29) below.

## Docs

| File | Description |
|---|---|
| [docs/reference/BACKEND.md](docs/reference/BACKEND.md) | Full backend reference — setup, architecture, API, config |
| [docs/blueprints/ValueInvestingRAG.md](docs/blueprints/ValueInvestingRAG.md) | Original RAG architecture blueprint |
| [docs/blueprints/ValueInvestingUI.md](docs/blueprints/ValueInvestingUI.md) | Frontend/UI architecture blueprint |
| [docs/blueprints/PortfolioAnalysis.md](docs/blueprints/PortfolioAnalysis.md) | Portfolio impact analyzer concept (future work) |
| [docs/blueprints/InsiderAndInstitutional.md](docs/blueprints/InsiderAndInstitutional.md) | Form 4 insider transactions & 13F institutional holdings (future work) |
| [docs/reference/FRONTEND_IMPLEMENTATION.md](docs/reference/FRONTEND_IMPLEMENTATION.md) | Full frontend reference (Next.js/React) |

## Session Log (2026-03-29)

### What was built this session

**Frontend Visual & Feature Upgrades (Gemini Takeover)**

- **Generative UI:** LLM can now render embedded `FinancialChart` (Recharts) in the chat response using a `<chart>` JSON tag.
- **Markdown Rendering:** Full `react-markdown` + `remark-gfm` integration for bold text, lists, and tables in assistant responses.
- **Active Filing Mode:** Selecting a filing from the sidebar scopes the chat to that specific document. A UI pill in the header indicates the filter, which can be cleared for global search.
- **Background Ingestion:** Both the Ingest Modal and the new Sidebar "Refresh" button use an asynchronous background task system with polling, preventing UI timeouts during large document processing.
- **Flexible Split-Pane:** Resizing limits expanded (5% to 95%) with `user-select` prevention for a smoother feel.
- **Dark Mode Source Panel:** Refactored the source viewer to a sleek GitHub-style dark theme with improved table styling.
- **Cleaner Sidebar:** Improved UI with better hierarchy, icons, and interactive hover states.

**Backend ↔ Frontend integration (was 0%, now fully working)**

- `GET /filings` endpoint — lists all ingested tickers/doc types with chunk counts
- Vite dev server proxy (`/api/*` → `http://localhost:8000`) so no CORS issues in dev
- `frontend/src/api.ts` — typed API client with `streamChat` (async SSE generator), `ingestFiling`, `listFilings`
- **Asynchronous Ingestion:** Added `BackgroundTasks` and `/ingest/status` polling endpoint to handle long-running SEC processing.
- **Explicit Filtering:** `POST /chat` now supports optional `ticker`, `year`, and `document_type` filters to enable scoped analysis.
- Table summarization made best-effort with fallback to raw text (no more crash on rate limit)

**Generative UI System Prompt**
- Updated `backend/api/main.py` with instructions for the synthesis LLM to output chart data for financial comparisons.

**Chunk quality improvements**

- `_merge_text_elements()` — consecutive paragraphs from the same section merged into ~2500 char page-sized chunks (was one element per paragraph)
- `_MIN_CHUNK_LENGTH` raised from 100 → 200 chars
- `_clean_table_html()` — **Fixed:** Preserves empty `<td>` cells for alignment; standardized currency/percentage merging.
- `_add_thead()` — detects header rows (no numeric cells) and wraps them in `<thead>` for correct CSS alignment

**Source panel visual improvements**

- HTML tables rendered via `dangerouslySetInnerHTML` instead of raw text
- AI summary box above each table (blue left-border callout)
- `<thead>` rows center-aligned (dates/labels), `<tbody>` rows right-aligned (numbers)
- Hover highlight on rows

**Bug fixes (Claude)**

- **Real SSE streaming:** `stream_generate` was wrapped in `list()` — buffered all tokens before sending. Fixed via a `threading.Thread` → `asyncio.Queue` bridge so tokens stream as they arrive.
- **Sidebar re-ingest spinner:** `getIngestStatus` was missing from imports; task ID format mismatch (`ticker-year-doctype` vs backend's `ticker-doctype-year`) meant spinner never appeared. Both fixed.
- **IngestModal:** `Loader2` icon missing from imports; success handler read nonexistent `result.chunks_stored`/`result.ticker` fields (backend is now async). Fixed with proper polling via `getIngestStatus`.
- **Split-pane resizing:** Added `minWidth: 0; overflow: hidden` to both panel wrappers so flex children shrink freely. Widened bounds from 5–95% → 2–98%.
- **SEC table layout:** Empty `<td>` spacer cells (SEC filing artifacts left after `$` merging) were expanding with `min-width: 40px` causing large gaps between data columns. Now collapsed to ~4px.

### Known issues / next to fix

- XBRL path returns 0 statements (edgartools 4.x API changed — `income_statement` etc. moved)
- Table header detection sometimes misclassifies period labels as data rows on complex tables
- `%` merge regex can incorrectly fire on rows where `%` is a standalone note cell
- 10-Q ingestion only fetches the most-recent filing for a given year (one quarter at a time); no bulk quarter ingestion
- Improvement: Citation Interactivity (Click [1] -> highlight Source 1).

---

## Quick Start

### Backend (Claude)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env  # fill in GOOGLE_API_KEY and SEC_USER_AGENT
uvicorn backend.api.main:app --reload
```

### Frontend (Gemini)
```bash
cd frontend
npm install
npm run dev
```

See [docs/reference/BACKEND.md](docs/reference/BACKEND.md) and [FRONTEND_IMPLEMENTATION.md](FRONTEND_IMPLEMENTATION.md) for full setup and usage.

---

## TODO

### Frontend
- [x] **State Management:** Real message state with SSE streaming (no Vercel AI SDK needed for now)
- [x] **Streaming Indicators:** `AgentState` connected to live backend SSE status events
- [x] **Backend Integration:** All API calls wired (`/chat`, `/ingest`, `/filings`)
- [x] **Ingest UI:** Modal with ticker/doc-type/year form, success/error feedback
- [x] **Source Panel:** Real retrieved chunks rendered as tabs; HTML tables rendered properly
- [x] **Clear button:** Resets chat + source panel
- [x] **Generative UI:** Support `<chart>` tags for embedded `FinancialChart` in chat responses
- [x] **Filings list in UI:** Show what's already ingested in Sidebar
- [x] **Responsive Refinement:** Flexible split-pane (2–98%) with `minWidth: 0` so panels shrink freely
- [x] **SEC Table layout:** Empty spacer cells collapsed; header rows centered; data columns right-aligned
- [ ] **Citation Interactivity:** Click citation badge → scroll SourcePanel to matching chunk
- [ ] **Bulk 10-Q ingestion:** Ingest all quarters for a given year in one action
- [ ] **Quarter filter in Filing Mode:** Sidebar selection and `/chat` currently filter by ticker/year/doc_type only — no way to scope a query to a single quarter. Add `quarter` to `ChatRequest` and the sidebar filing selector.

### Backend
- [x] End-to-end test with real ticker (AAPL 10-Q ingested and queried successfully)
- [x] Tables correctly separated from narrative text via `unstructured`
- [x] `_MIN_CHUNK_LENGTH` tuned (200 chars)
- [x] Text elements merged into page-sized chunks (~2500 chars)
- [x] `GET /filings` endpoint added
- [x] Table HTML cleaned (empty cells preserved, `$`/`%` cell merging, `<thead>` detection)
- [x] **Background task queue** for `/ingest` (using FastAPI `BackgroundTasks`)
- [x] **Explicit filters** in `/chat` (ticker, year, doc_type)
- [x] **Real SSE streaming** — token-by-token via thread→Queue bridge (was buffered)
- [ ] Fix XBRL path — edgartools 4.x moved `income_statement` / `balance_sheet` attributes
- [ ] Handle 10-Q quarter inference more robustly (overlapping month ranges)
- [ ] Improve `_add_thead` — misclassifies some complex multi-row headers
- [ ] Support bulk 10-Q ingestion (all quarters for a year)

### RAG Quality
- [ ] Evaluate retrieval precision — are the right chunks coming back for test queries?
- [ ] Test `claude-sonnet-4-6` vs `gemini-2.5-pro` for synthesis quality on financial queries
- [ ] Add re-ranking step (cross-encoder) before passing chunks to synthesis LLM
- [ ] Experiment with overlapping windows (parent-doc retrieval) for better context

### Infrastructure
- [ ] Add `.gitignore` entries for `data/lancedb/` and `.env`
- [ ] Upgrade Python to 3.11+ (3.9 is EOL, Google SDKs warn on every import)
- [ ] Lock down CORS (`allow_origins=["*"]` is fine for local dev only)
- [ ] Add structured logging

### Future / Portfolio Analyzer
- [ ] Merge `PortfolioAnalysis.md` concept into this repo
- [ ] LangGraph DAG for supply chain risk extraction
- [ ] Neo4j knowledge graph for portfolio intersection queries

### Future / Insider & Institutional Data
- [ ] Form 4 insider transaction tracker — see `docs/blueprints/InsiderAndInstitutional.md`
- [ ] 13F institutional holdings tracker (Berkshire, Sequoia, etc.)
- [ ] "Cluster buying" alert: flag when multiple insiders buy within 30 days
