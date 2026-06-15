# Project Status & Handoff — Mosaic

> **Purpose:** A cold-start handoff — what Mosaic is, how to run it, the
> environment gotchas, and the architecture invariants not to break. For the
> live backlog and the dated history of what changed, see
> [`docs/TODO.md`](./TODO.md) (rounds 1–7 + audits). This doc stays lean and
> current; TODO wins on any conflict.
>
> **Last updated:** 2026-06-15 (round 7 + rebrand ValueRAG → Mosaic).

---

## 1. What Mosaic is

An **autonomous equity-research analyst** over SEC filings (10-K / 10-Q). Ask
about any company in plain language; the agent fetches its filings from EDGAR on
demand, answers with **cited figures** and generative **charts**, tracks
**insider (Form 4)** and **superinvestor (13F)** activity, and **self-verifies**
its numbers against the retrieved sources.

- **Backend:** FastAPI + LanceDB (local, on-disk vector store). Ingestion has two
  concurrent paths — **(A)** narrative HTML via `unstructured`, **(B)** structured
  financial statements via XBRL (`edgartools`). Tables are batch-summarized by a
  fast LLM before embedding. Answers stream over SSE.
- **Agent:** a multi-tool **ReAct loop** (`backend/agent/`) — tools: search the
  corpus, **auto-ingest a missing filing**, list the corpus, insider activity,
  fund holdings, and "which superinvestors hold X". Then a **self-verification**
  critic pass. Provider-agnostic text-ReAct by default; native Gemini
  function-calling is opt-in (`agent_native_tools`).
- **Embeddings:** **local by default** (`local-bge-large`, fastembed/ONNX, CPU,
  no key/quota). Only synthesis + the fast model need an API key.
- **Frontend:** React + Vite + TS, Tailwind v4, **3 themes** (Study / Modern-Dark
  / Modern-Light, toggle persisted), insider + smart-money sidebar panels that
  follow the conversation, multi-series comparison charts, chat persistence. There
  is **no manual ingest UI** — the agent ingests on demand.

Run:
```bash
./.venv/bin/uvicorn backend.api.main:app --reload   # backend :8000
cd frontend && npm run dev                           # Vite :5173, proxies /api → :8000
./.venv/bin/python -m pytest backend/tests -q        # backend tests (247)
cd frontend && npm test                              # frontend tests (57)
```

Related docs: [`docs/TODO.md`](./TODO.md), [`reference/BACKEND.md`](./reference/BACKEND.md),
[`reference/FRONTEND_IMPLEMENTATION.md`](./reference/FRONTEND_IMPLEMENTATION.md),
[`UX_AUDIT.md`](./UX_AUDIT.md), [`VISUAL_AUDIT.md`](./VISUAL_AUDIT.md),
[`HOSTING_AND_AI_OPTIONS.md`](./HOSTING_AND_AI_OPTIONS.md). The `blueprints/` are
historical origin docs (banners mark what's since shipped or diverged).

---

## 2. Environment gotchas (read before running)

1. **Use `./.venv/bin/python` directly.** The venv is on **Python 3.14**
   (rebuilt 2026-06-15). `source .venv/bin/activate` may not be on PATH in every
   shell — invoking the interpreter path always works.
2. **A real `GOOGLE_API_KEY` is in `.env`** (free tier). Embeddings are local so
   ingest + retrieval need no key; **synthesis + the fast model do**. The binding
   constraint is the **free-tier per-DAY generation cap** (`gemini-2.5-flash` /
   `-flash-lite`) — heavy use exhausts it; a paid key (pennies/mo) removes it.
   Embeddings also have a per-minute cap on the *hosted* embedder, but local is
   the default so that's moot unless you switch.
3. **Switching the embedding model requires a re-ingest.** `EMBEDDING_DIM` is
   baked into the LanceDB schema at table creation (`local-bge-large` = 1024-dim).
   To change: drop `data/lancedb` (regenerable) and re-ingest.
4. **`data/lancedb` + `data/cache` are gitignored, regenerable.** The smart-money
   index (`data/cache/smart_money_index.json`) auto-refreshes on startup if stale.
5. **LanceDB specifics:** `to_pandas()` takes no `columns=` — project via
   `table.search().select([...]).limit(n)`. A cached table handle is a snapshot;
   `store.py` pins strong read-consistency and re-opens per call. ANN index is
   gated behind a 256-row threshold.
6. **edgartools APIs (verified live):** XBRL statements are methods on
   `xbrl.statements` (`income_statement()`, `balance_sheet()`,
   `cashflow_statement()`); Form 4 → `filing.obj().to_dataframe()`; 13F →
   `filing.obj().infotable`. Identity is set from `SEC_USER_AGENT` in
   `edgar_fetcher.py`. EDGAR needs no API key.

---

## 3. Current state (2026-06-15)

- ✅ **247 backend** tests + **57 frontend** tests green; build clean.
- ✅ **Live-verified:** full ingest (AAPL 10-Q, ~8s with local embeddings),
  agentic chat with cited figures + chart + `supported` verification, ReAct loop
  driving multiple tool calls, holdings trackers (AAPL insiders; Berkshire 13F),
  smart-money index (11 funds / 319 positions), all 3 themes.
- ⏳ **Quota-deferred (see TODO → TEST-LATER):** a clean local-vs-Gemini embedding
  A/B and a full live agent-with-tools run that triggers a real auto-ingest — both
  blocked only by the free-tier daily generation cap, not by code.
- Work is on the **`feat/agentic-latency`** branch.

The full dated history (rounds 1–7, the audits) lives in `docs/TODO.md`.

---

## 4. Architecture invariants (don't break these)

- `ingest_filing(ticker, document_type='10-K', year=None, on_progress=None) -> int`
  stays **synchronous** (called via `asyncio.to_thread`); `on_progress` must be
  exception-safe.
- **Table summarization is BATCHED** (`summarize_tables`, `table_summary_batch_size`
  per LLM call) and PATH A/B run **concurrently** — this is what keeps ingest fast
  under a rate-limited provider. Don't revert to per-table calls.
- All values interpolated into LanceDB `where`/`delete` go through
  `backend/retrieval/filters.py` (allowlist + escape; incl. `validate_iso_date`).
  Never f-string raw.
- **Provider routing is by model-name prefix** (`claude-`/`gemini-`/`gpt-`/`o*`,
  and `local-*` for embeddings) in `llm.py` + `embedder.py`. `EMBEDDING_DIM` is
  fixed at table creation → re-ingest to change the embedder.
- **Agent decision logic is pure + injectable** (`backend/agent/planner.py`,
  `react.py`): `plan_auto_ingest`, `parse_action`, `verify_answer`, the ReAct loop
  (injected generate/retrieve/ingest/tool fns). Keep it testable without a key.
- **Holdings are EDGAR-only** (`backend/holdings/`): aggregation logic pure, fetch
  injectable. Smart-money tracks a **curated** fund universe (`funds.json`);
  "which funds hold X" is the curated set, not all ~5k filers (EDGAR has no
  global reverse-index).
- **SSE event shape:** `{"type": ..., "data": ...}`, type ∈
  `status|agent_step|chunk|verification|sources|error|done` (see the `/chat`
  docstring). Adding a type is backward-safe.
- **Theming:** Tailwind v4 `@theme` vars are the Study defaults; `html[data-theme]`
  blocks redefine the same vars (components unchanged). Per-theme overrides
  neutralize the Study-only atmosphere (`body` grain, `.vr-foil`, `.vr-paper`) and
  swap fonts; `--color-on-accent` keeps primary-button text readable.
- Frontend↔backend contract types live in `frontend/src/api.ts`.
- Chat is **multi-turn** (bounded history in the synthesis prompt + history-aware
  query reformulation) and **persisted** client-side (localStorage) — not stateless.

---

## 5. How to verify after changes

```bash
./.venv/bin/python -m pytest backend/tests -q        # 247+ must stay green
./.venv/bin/python -c "from backend.api.main import app"   # import smoke
cd frontend && npm run build && npm test             # clean + 57 green
# Live (needs GOOGLE_API_KEY; watch the free-tier daily cap):
./.venv/bin/python -c "from backend.pipeline.ingest import ingest_filing; print(ingest_filing('AAPL','10-Q'))"
```

When dispatching subagents: frontend agents self-verify with `npm`; backend
agents can run `./.venv/bin/python -m pytest`. The orchestrator should still
re-run the suite and a live smoke (where the quota allows) after integrating.
