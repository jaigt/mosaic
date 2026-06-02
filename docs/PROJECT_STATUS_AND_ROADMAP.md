# Project Status & Roadmap — Value Investing RAG

> **Purpose:** Single source of truth for the current state of the codebase, what
> has been done, what remains, and how to continue. Written as a handoff so a
> future session (human or agent) can pick up cold. Keep this updated.
>
> **Last updated:** 2026-06-02 (round 2: RAG quality + ops + design system, all committed)
>
> 👉 **For the live, prioritized to-do list, see [`docs/TODO.md`](./TODO.md).** This
> doc is the background/architecture/what's-done handoff; TODO.md is the actionable
> checklist. Sections §5/§6 below are kept for narrative context but TODO.md wins on conflict.

---

## 1. What this project is

A local, multi-provider RAG pipeline over SEC filings (10-K / 10-Q). Backend is
FastAPI + LanceDB (local vector store); frontend is React + Vite + TypeScript.
Ingestion has two paths: **(A)** narrative HTML via `unstructured`, and **(B)**
structured financial statements via XBRL (`edgartools`). Tables are summarized by
a fast LLM before embedding; synthesis answers stream over SSE.

- **Backend entry:** `uvicorn backend.api.main:app --reload`
- **Frontend:** `cd frontend && npm run dev` (Vite proxies `/api/*` → `:8000`)
- **Tests:** `source .venv/bin/activate && python -m pytest backend/tests/ -q`
- **Frontend build/typecheck:** `cd frontend && npm run build`

Related docs: `docs/reference/BACKEND.md`, `docs/reference/FRONTEND_IMPLEMENTATION.md`,
`docs/blueprints/*`, and the original code review `REVIEW.md` (root, Codex, 2026-04-29).
Memory index: `~/.claude/projects/.../memory/MEMORY.md`.

---

## 2. ENVIRONMENT GOTCHAS (read before running anything)

1. **`GOOGLE_API_KEY` in `.env` is currently INVALID/expired.** Gemini returns
   `400 API_KEY_INVALID`. This blocks any **live ingest** (table summarization +
   embedding) and **live chat/retrieval** (query embedding + synthesis). All
   EDGAR/XBRL fetching works (no Google key needed). **Refresh this key** to do a
   real end-to-end ingest. This is the single thing preventing full live verification.
2. **Python 3.9** (EOL). Google SDKs emit `FutureWarning` on import; urllib3 warns
   about LibreSSL. Works, but upgrade to 3.11+ is a tracked task.
3. **Subagents can't run Python/pytest in their sandbox** — when dispatching agents
   to change backend code, they cannot self-verify. The orchestrator must run
   `pytest` + live smokes after they finish. (Frontend agents can run `npm`.)
4. **LanceDB specifics (v0.27.1):**
   - `to_pandas()` does NOT accept `columns=`. To project columns use
     `table.search().select([...]).limit(n).to_pandas()` (needs explicit limit;
     use `table.count_rows()`).
   - `to_lance()` needs `pylance` installed (it isn't) — don't rely on it.
   - A cached/long-lived table handle is a **snapshot**: with default
     `read_consistency_interval=None` it won't see rows written later. We pin the
     cached connection to `timedelta(0)` AND re-open the table per call (see `store.py`).
   - IVF_PQ index needs enough rows to train; indexing is gated behind a 256-row threshold.
5. **edgartools 4.x XBRL API** (verified live): statements are on the
   `.statements` accessor as **methods**: `xbrl.statements.income_statement()`,
   `.balance_sheet()`, `.cashflow_statement()` (note `cashflow_statement`, NOT
   `cash_flow_statement`) → each returns a `Statement` with `.to_dataframe()`.
   The period-end date is `filing.period_of_report`.

---

## 3. Current state (after this engagement)

**Verification status as of last update:**
- ✅ `pytest backend/tests/` → **99 passed**
- ✅ `npm run build` → clean (only the pre-existing recharts chunk-size advisory);
  `npm test` (Vitest) → 9 passed
- ✅ All work **committed** on `develop` (6 commits: backend security/correctness,
  frontend XSS/perf, housekeeping, backend RAG, backend ops, frontend design system)
- ✅ Live XBRL extraction (AAPL 10-Q) → 3 statements
- ✅ Live `/filings` aggregate → works
- ✅ Refactored ingestion runs end-to-end through parse + parallel table
  summarization (raw-text fallback confirmed); **only** fails at the Google
  embedding call due to the invalid key (§2.1)
- ✅ Index intact (36 rows; aborted live ingest did not corrupt it)
- ⏳ NOT verified live: actual Gemini summarization/embedding/synthesis round-trips
  (blocked on the API key)

**All work is committed** on `develop` (was uncommitted at the previous update).

### 3.1 Second round (RAG quality + ops + design system) — committed
Dispatched as 3 parallel agents with strict file-ownership partitioning, then
integrated + verified by the parent:
- **RAG quality** (`backend/retrieval/`): hybrid retrieval (RRF + BM25-lite, no
  FTS index), MMR diversification, history-aware query reformulation
  (condense-question, graceful fallback). Wired into `_chat_stream` retrieval
  (retrieval only; synthesis still uses the original message). **No new deps.**
- **Ops robustness** (`backend/api/`): bounded SSE queue + client-disconnect
  handling (stops the paid LLM producer when the client leaves), typed ingest
  task state (backward-compatible endpoints), X-Request-ID middleware +
  structured `log_event`.
- **Design system** (`frontend/`): Tailwind v4 (CSS-first) + "Ledger Terminal"
  token layer + `ui/` primitives (Button/Input/Select/Modal/Badge/Card/Spinner),
  components refactored onto them; Vitest added.
- **Cross-agent fix:** SSE `error` data kept a plain string (frontend contract) —
  request_id moved to logs + `ref:` suffix rather than an object payload.
- Still blocked on the invalid `GOOGLE_API_KEY` for live LLM round-trips.

---

## 4. Work completed this engagement

### 4.1 Audit (4 parallel deep-dive agents)
Produced verified findings across backend correctness, performance, frontend, and
security. Key verified discoveries (some corrected the initial pass):
- XBRL path was **100% dead** (0 statement chunks ever written) — wrong attribute API.
- Quarter inference was **actively mislabeling** data (overlapping month ranges).
- LanceDB filter injection was **proven exploitable** (filter bypass + unintended
  row deletes via a crafted ticker).
- All loading spinners were **frozen** (missing `@keyframes spin`).
- Vector search is **brute-force** (no ANN index ever created).
- LanceDB connection **reopened on every request**; `/filings` did 2 full table
  scans + a dead `df`.
- Embedding dimension drift was **refuted** (3072 consistent end-to-end); embedding
  `task_type` and `.where()` prefilter semantics are **correct** — don't "fix" these.

### 4.2 P0 batch — correctness + security quick wins (DONE, verified)
| Area | Change | Files |
|---|---|---|
| XBRL revival | edgartools 4.x `statements.<method>()` API (verified 0→3 live) | `backend/ingestion/xbrl_parser.py` |
| Quarter fix | derive calendar quarter from `period_of_report`; pure `_calendar_quarter`/`_infer_quarter` | `backend/ingestion/edgar_fetcher.py` |
| Injection | new validation/escaping module; wired into search + delete clauses | `backend/retrieval/filters.py`, `retriever.py`, `pipeline/store.py` |
| Schema | `ChatRequest.document_type` loosened `str` → `Literal` | `backend/models/schemas.py` |
| CORS | locked to `settings.cors_allow_origins` (default Vite origin) | `backend/api/main.py`, `config.py` |
| XSS | DOMPurify sanitize of SEC table HTML; moved injected `<style>` → `index.css` | `frontend/src/components/SourcePanel.tsx`, `index.css` |
| Git hygiene | `git rm --cached data/lancedb`; rewrote `.gitignore` | `.gitignore` |
| Frontend quick wins | relevance score `1/(1+d)`; `activeIdx` reset; `@keyframes spin`; chart `title` passthrough; year `max`=current year | `SourcePanel.tsx`, `Message.tsx`, `IngestModal.tsx`, `index.css` |
| `/filings` | dropped dead `df`; single projected pass; proper 500 on error | `backend/api/main.py` |

### 4.3 P1 batch — performance + last security gap (DONE, verified by tests/build)
Dispatched as 3 file-disjoint parallel agents + inline auth work:
| Area | Change | Files |
|---|---|---|
| Ingestion: single EDGAR resolve | `resolve_filing()` once → `html_from_filing()`/`xbrl_from_filing()` share the filing object (was resolving twice) | `backend/ingestion/edgar_fetcher.py`, `pipeline/ingest.py` |
| Ingestion: parallel table summarization | `ThreadPoolExecutor` + thread-safe `TokenBucket`, replacing serial `sleep(0.5)`; ordering/chunk_id preserved; raw-text fallback intact | `backend/pipeline/ingest.py`, `pipeline/ratelimit.py` (new) |
| Storage: connection cache | process-wide cached `lancedb.connect`, strong read-consistency, table re-opened per call | `backend/pipeline/store.py` |
| Storage: ANN index | guarded cosine IVF_PQ index, no-op below 256 rows | `backend/pipeline/store.py` |
| Frontend: render perf | stable message IDs + `React.memo`; hoisted markdown `components`; memoized chart parse + `FinancialChart`; throttled/near-bottom scroll | `ChatPanel.tsx`, `Message.tsx`, `Visualizer/FinancialChart.tsx` |
| Frontend: abort | `AbortController` + signal in `streamChat`; **Stop button**; abort on clear/unmount; graceful `AbortError` | `frontend/src/api.ts`, `ChatPanel.tsx` |
| Security: auth + rate limit | optional `X-API-Key` (off when unset) + per-IP token-bucket limiter on `/ingest`,`/chat`,`/retrieve` | `backend/api/security.py` (new), `main.py`, `config.py` |

### 4.4 Tests added (TDD)
- `backend/tests/test_quarter_inference.py` — quarter logic incl. boundary regressions
- `backend/tests/test_filters.py` — validation/escaping + injection rejection
- `backend/tests/test_security.py` — token bucket, rate limiter, API-key check
- `backend/tests/test_ratelimit.py` — thread-safe blocking token bucket (ingestion)
- `backend/tests/test_ingest_concurrency.py` — parallel summarization order/concurrency/fallback
- `backend/tests/test_store_cache.py` — connection reuse + write visibility + index no-op
- `backend/tests/test_history.py` — multi-turn history formatting (bounds, truncation, malformed-entry skip, current-message dedupe)
- Added `pytest>=8.0.0` to `backend/requirements.txt`; `dompurify` to frontend deps.

### 4.6 Multi-turn chat (DONE, verified by tests) — closes review item #7
- `_format_history()` in `backend/api/main.py` renders bounded prior turns (last 6,
  ≤1000 chars each, malformed entries skipped) and drops the trailing duplicate of the
  live message (frontend appends it before sending).
- `_chat_stream` now injects a `CONVERSATION SO FAR` block into the synthesis prompt when
  history is present, so the model can resolve follow-up references.
- **Still stateless on the retrieval side**: the vector query is still just the raw latest
  message, so a bare follow-up ("what about 2023?") may retrieve poorly. Next step is
  history-aware query reformulation (condense-question pattern) — see §6.

### 4.5 New config knobs (`backend/config.py`)
- `cors_allow_origins: list[str] = ["http://localhost:5173"]`
- `api_key: str = ""` (empty = auth disabled)
- `rate_limit_per_minute: int = 30` (0 = disabled)

---

## 5. NOT done yet / known gaps

### Immediate / loose ends
- **Refresh `GOOGLE_API_KEY`** and run a real end-to-end ingest + chat to close
  live verification (§2.1, §3). This is the top loose end.
- **Frontend API-key plumbing:** when `api_key` is set server-side, `frontend/src/api.ts`
  must send the `X-API-Key` header on `/chat`,`/ingest`,`/retrieve`. Not yet wired
  (fine while auth is disabled by default).
- **Nothing committed** — decide on commit/PR structure (suggest 2 commits:
  "P0: correctness + security", "P1: performance + auth").
- **Stale index row:** the one existing AAPL row keeps its old quarter label until
  re-ingested; new ingests are correct.
- **Benign warnings:** `table_names()` deprecation (use `list_tables()`), pydantic
  class-`Config` deprecation (use `ConfigDict`), Python 3.9 EOL.

### P1 remainder (not yet done)
- Frontend streaming-state: the biggest render win (keeping in-flight text fully
  out of the `messages` array) was partially addressed via memoization; consider a
  dedicated streaming slice if profiling shows need.
- SSE robustness: bounded queue / backpressure + disconnect-aware producer in
  `_chat_stream`; durable/bounded `_ingest_tasks` (currently in-memory, unbounded,
  lost on restart, per-worker).

### P2 — the big rocks (not started)
- **Styling system:** the frontend is ~100% inline styles. Recommended: **Tailwind v4**
  with `:root` promoted to `@theme`, plus `ui/` primitives (`Button`, `Panel`,
  `IconButton`, `Badge`), migrated file-by-file. Detailed plan in the frontend
  audit (see §6). Biggest unblock for future visual work.
- **Test harness for frontend:** add Vitest + React Testing Library before the
  styling migration to catch regressions.
- **RAG quality:** chunk overlap in `_merge_text_elements` (currently hard 2500-char
  cut, no overlap); re-ranking (cross-encoder) over a wider candidate set;
  hybrid/FTS search; row-aware source truncation in `_format_sources` (currently
  truncates `raw_payload[:2000]`, can cut tables mid-row).

### P3 — cleanup / UX (not started)
- Axe or wire dead UI: Sidebar "Query History/Settings/Sign Out", SourcePanel
  Search/Download/Maximize2 icons. (Download/Maximize2 are cheap wins — sketches in
  frontend audit.)
- Clickable citations: clicking `[1]` / a source pill scrolls SourcePanel to that
  source (needs lifting source state or Context).
- Accessibility: real `<button>`s (many clickable `<div>`s), `aria-label`s, modal
  focus trap + Esc/backdrop close, ErrorBoundary at root.
- Responsive layout (desktop-only today); window-scoped resize listeners.
- ~~`conversation_history` is sent + accepted but **not used** in synthesis~~ —
  **DONE** (§4.6): bounded history now injected into the synthesis prompt. Retrieval-side
  reformulation still pending (see §6).

### Correctness follow-ups (from backend audit, not yet done)
- **Table HTML cleanup uses regex** (`_clean_table_html`/`_add_thead` in `ingest.py`):
  fragile on nested tables, `<th>`, colspans, multi-row headers. Recommend moving to
  `lxml`/`bs4` (already transitive deps via unstructured), OR rely on XBRL for core
  statements now that path B works.
- **Store period_of_report as a metadata column** for unambiguous date filtering
  (current `filing_quarter` is calendar-quarter, which differs from fiscal quarter
  for off-cycle filers like AAPL). Requires a schema change + re-ingest.
- `index_offset` param in `_elements_to_chunks` is currently unused (no live
  collision because there's a single enumeration pass) — leave or remove; revisit if
  ingestion is ever split per-path.
- `filing_quarter` can be `"Q?"` from `_infer_quarter(None)` which would fail the
  `DocumentChunk` Literal — in practice the caller always passes a real date, so it
  never triggers; tighten if that invariant ever changes.

---

## 6. Full prioritized roadmap (forward-looking)

1. **Refresh GOOGLE_API_KEY → live e2e verify.** (loose ends — STILL THE TOP
   BLOCKER; all code below is tested but not live-verified end to end.)
2. **Auth follow-through:** frontend `X-API-Key` header when configured.
3. ~~P2 styling system~~ **DONE (§3.1)** — Tailwind v4 + `ui/` primitives + Vitest.
   Visual polish work is now unblocked.
4. **RAG quality:** ~~reformulation, re-ranking, hybrid search~~ **DONE (§3.1)**;
   remaining: chunk overlap, row-aware table truncation, eval harness to measure
   whether hybrid/MMR actually help on real queries.
5. ~~SSE/ops robustness~~ **DONE (§3.1)** — bounded queue, disconnect handling,
   typed ingest tasks, structured logging + request IDs. Remaining: cross-process
   durability (Redis/Celery) if it ever goes multi-worker.
6. **P3 UX:** clickable citations, axe/wire dead UI, accessibility, responsive.
7. **Infra:** Python 3.11+, lock deps (`uv`/`pip-tools`), fix deprecation warnings,
   move table cleanup off regex.
8. **Future features** (blueprints exist): bulk 10-Q ingestion, portfolio analyzer,
   Form 4 / 13F trackers.

---

## 7. Architecture notes & invariants (don't break these)

- `ingest_filing(ticker, document_type='10-K', year=None) -> int` must stay
  **synchronous** — `main.py` calls it via `asyncio.to_thread`.
- `get_table()`, `upsert_chunks()`, `generate_chunk_id()` public signatures are
  depended on across modules — keep stable.
- All values interpolated into LanceDB `where`/`delete` MUST go through
  `backend/retrieval/filters.py` (allowlist + quote-escape). Never f-string raw.
- LLM/embedding provider routing is by **model-name prefix** (`claude-`/`gemini-`/
  `gpt-`/`o*`) in `backend/pipeline/llm.py` + `embedder.py`. `EMBEDDING_DIM` is baked
  into the LanceDB schema at table creation — changing the embedding model requires a
  new table / re-ingest.
- SSE event shape: `{"type": "status"|"chunk"|"sources"|"done"|"error", "data": ...}`.
- Frontend↔backend contract types live in `frontend/src/api.ts`.
- Chat is **stateless per request** today (see `conversation_history` gap in §5).

---

## 8. How to verify after changes

```bash
# Backend
source .venv/bin/activate
python -m pytest backend/tests/ -q            # must stay green (44+)
python -c "from backend.api.main import app"  # import smoke

# Frontend
cd frontend && npm run build                  # tsc + vite, must be clean (strict noUnusedLocals)

# Live (needs valid GOOGLE_API_KEY):
python -c "from backend.pipeline.ingest import ingest_filing; print(ingest_filing('AAPL','10-Q'))"
```

When dispatching parallel agents on backend code, remember they can't run pytest
(§2.3) — verify their work yourself, including a live smoke where credentials allow.
