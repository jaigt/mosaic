# Project Status & Handoff — Mosaic

> **Purpose:** A cold-start handoff — what Mosaic is, how to run it, the
> environment gotchas, and the architecture invariants not to break. For the
> live backlog and the dated history of what changed, see
> [`docs/TODO.md`](./TODO.md). This doc stays lean and current; TODO wins on any
> conflict.
>
> **Last updated:** 2026-06-15 (local-first / oMLX round). Repo: `github.com/jaigt/mosaic`.

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
- **Models:** provider-agnostic routing by model name. Prefix families
  (`claude-`/`gemini-`/`gpt-`/`o*`) **plus** a `"<provider>/<model>"` form for
  OpenAI-compatible servers — `cerebras`/`groq`/`mistral` (free cloud tiers) and
  `ollama`/`mlx` (local). The current POC default is **fully local on oMLX**
  (synthesis `mlx/Qwen3.5-27B-Claude-distill`, fast/agent `mlx/gemma-4-12B`) — $0,
  offline, no rate limits. `AGENT_MODEL` can point the ReAct loop at a faster
  model than synthesis.
- **Embeddings:** **local by default** (`local-bge-large`, fastembed/ONNX, CPU,
  no key/quota). With a local LLM too, the whole stack needs no API key.
- **Frontend:** React + Vite + TS, Tailwind v4, **3 themes** (Study / Modern-Dark
  / Modern-Light, toggle persisted), insider + smart-money sidebar panels that
  follow the conversation, multi-series **theme-aware** comparison charts, chat
  persistence. There is **no manual ingest UI** — the agent ingests on demand.

Run (local-oMLX layout — oMLX serves on :8000, so the backend uses :8008):
```bash
./.venv/bin/uvicorn backend.api.main:app --port 8008  # backend :8008
cd frontend && npm run dev                            # Vite :5173, proxies /api → :8008
./.venv/bin/python -m pytest backend/tests -q         # backend tests (268)
cd frontend && npm test                               # frontend tests (57)
```
(Default `:8000` is fine if you're not running a local model server on it; the
Vite proxy target is overridable via `BACKEND_URL`.)

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
2. **No API key is required for the default local stack.** `.env` selects models
   via `FAST_MODEL`/`SYNTHESIS_MODEL`/`AGENT_MODEL`; the POC default points them at
   a local **oMLX** server (`mlx/<model>`, `MLX_BASE_URL` + optional `MLX_API_KEY`).
   Cloud fallbacks are optional: a free **Cerebras** key (`cerebras/<model>`,
   ~1M tok/day) or **Gemini** (`gemini-*`, but a stingy free per-day cap — the
   reason we moved local). Whatever the LLM, **embeddings stay local** (no key).
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

- ✅ **268 backend** tests + **57 frontend** tests green; build clean.
- ✅ **Live-verified on the local oMLX stack:** AAPL queries (cited figures +
  theme-aware chart + `supported` verification) and the **full AAPL/MSFT/GOOGL
  comparison end-to-end** (auto-ingest of the missing tickers during testing,
  accurate figures, multi-company chart, reliable Gemma tool-call JSON). Holdings
  trackers + smart-money index verified earlier; all 3 themes verified in-browser.
- Latest work merged to **`develop`** (pushed). The old free-tier-quota blocker is
  resolved by running fully local — see `docs/TODO.md` for the current backlog.

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
- **Provider routing is by model name** in `llm.py`: prefix families
  (`claude-`/`gemini-`/`gpt-`/`o*`) plus `"<provider>/<model>"` for
  OpenAI-compatible endpoints (`cerebras`/`groq`/`mistral`/`ollama`/`mlx`) via a
  `base_url` swap; transient 429s retry with backoff (`_with_retry`). Embeddings
  route by `local-*` in `embedder.py`; `EMBEDDING_DIM` is fixed at table creation
  → re-ingest to change the embedder.
- **The LanceDB store self-migrates** (`store.py` `_migrate_schema`): columns in
  `_SCHEMA` missing from an existing table are backfilled on open, so adding a
  metadata column never requires wiping the corpus.
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
./.venv/bin/python -m pytest backend/tests -q        # 268+ must stay green
./.venv/bin/python -c "from backend.api.main import app"   # import smoke
cd frontend && npm run build && npm test             # clean + 57 green
# Live (local stack — no key needed; ingest uses local embeddings + EDGAR):
./.venv/bin/python -c "from backend.pipeline.ingest import ingest_filing; print(ingest_filing('AAPL','10-Q'))"
```

When dispatching subagents: frontend agents self-verify with `npm`; backend
agents can run `./.venv/bin/python -m pytest`. The orchestrator should still
re-run the suite and a live smoke (where the quota allows) after integrating.
