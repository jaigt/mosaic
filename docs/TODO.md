# TODO — Mosaic (formerly ValueRAG)

Single source of truth for outstanding work. Prioritized, with file pointers.
Companion to `docs/PROJECT_STATUS_AND_ROADMAP.md` (background, architecture
invariants, what's already done). **Keep this file updated** — check items off,
add new ones, move things between sections as priorities shift.

Last reconciled against code: 2026-06-09 (after round 3: config-drift fixes,
synthesis-error surfacing, citation UX, chunk overlap, deprecation cleanup).

Status legend: `[ ]` not started · `[~]` partial · `[x]` done (leave briefly for context, then prune)

---

## P0 — Blockers (mostly cleared 2026-06-15; see notes)

- [x] **Real `GOOGLE_API_KEY` set + live-verified (2026-06-15).** Auth confirmed
      via `models.list()`. The configured `gemini-3.5-flash` /
      `gemini-3.1-flash-lite` names were **invalid** (don't exist; only
      `*-preview` do) — now pinned to stable GA `gemini-2.5-flash` /
      `gemini-2.5-flash-lite`, verified working. Embedding `gemini-embedding-001`
      live at 3072-dim.
- [x] **Live end-to-end smoke PASSED.** Full ingest (AAPL 10-Q: fetch→parse→
      batch-summarize 21 tables→embed 52 chunks→store) in **8.4s**. Chat: live
      retrieval → synthesis with a real cited figure + a generative `<chart>` →
      self-verification returned `supported`. Auto-ingest-on-miss fires
      correctly for an absent ticker (MSFT). Stale AAPL rows refreshed (36→52).
- [ ] **FREE-TIER EMBEDDING QUOTA is the binding constraint.**
      `embed_content_free_tier_requests` = 100/min (+ a daily cap) on
      `gemini-embedding-001`. A full fresh ingest can exhaust it; the embedder
      now retries/backs off on 429 (up to ~60s) and ingest degrades gracefully,
      but a large multi-filing ingest will be quota-throttled. **This makes the
      "local embeddings" item below the highest-value infra step** — it removes
      the embedding key dependency entirely (only synthesis would need a key).

---

## P1 — "Finish the frontend" (the visible polish gaps)

- [ ] **Empty/loading/error states pass.** Now that synthesis errors are
      surfaced (not silently swallowed), review the real states post-P0:
      first-run (no filings), mid-ingest, retrieval-returned-nothing,
      backend-down, synthesis-error. Make sure each looks intentional.
- [x] **Accessibility sweep (2026-06-15).** App-root `ErrorBoundary`; Modal focus
      trap (Tab/Shift+Tab/Esc/backdrop); aria-live on ingest progress; icon
      buttons + Sidebar rows audited (already had labels/handlers).
- [x] **Responsive layout (2026-06-15).** Below the `md` breakpoint the sidebar
      collapses to an overlay drawer and panels stack (`useMediaQuery` hook);
      desktop split-pane unchanged.
- [ ] **Inline `[1]` markers in answer text.** Source *pills* are now clickable
      and focus the SourcePanel; making the inline `[1]`/`[2]` markers inside
      the markdown clickable too needs a custom react-markdown text renderer.

---

## P2 — RAG quality (improve answer quality)

- [~] **Evaluation harness.** Scaffolding DONE (2026-06-15): pure scorer
      (`backend/eval/metrics.py` — hit@k, MRR, section/ticker matching),
      injectable live runner (`backend/eval/harness.py`,
      `python -m backend.eval.harness`), and a seed set
      (`backend/eval/eval_set.json`, 8 AAPL cases). All scoring is unit-tested
      without a key. First live run (2026-06-15, local-bge-large over AAPL 10-K):
      MRR=0.5, hit@5=0.5 — all 4 NARRATIVE cases hit at rank 1; all 4
      FINANCIAL-STATEMENT cases missed, but that's confounded (raw-table fallback
      + overly strict `section_contains` labels that reject a correct MD&A
      retrieval). REMAINING: refine the section labels (allow MD&A for revenue
      qs), re-run with proper summaries, expand beyond AAPL.
- [ ] **Tune reformulation/hybrid/MMR/overlap params** against the eval harness
      (overfetch factor, `mmr_lambda`, RRF `k`, `_TEXT_CHUNK_OVERLAP`,
      `should_reformulate` thresholds).
- [x] **Local embeddings DONE (2026-06-15).** `local-*` route in `embedder.py`
      via `fastembed`/ONNX (CPU, no key, no quota): `local-bge-large` (1024d,
      now the DEFAULT), `-base` (768d), `-small` (384d). Removes the embedding
      quota wall — only synthesis/fast use a key now. Verified live: AAPL
      10-K/10-Q ingested with 100% local embeddings. NOTE: different vector
      space + dim than gemini-embedding-001 → re-ingest required when switching
      (drop the `sec_chunks` table). bge-large download is ~1.2GB on first use.
- [ ] **Clean embedding A/B (local-bge-large vs gemini-embedding-001).** Blocked
      2026-06-15 on free-tier quota: the local-embedding eval ran but the corpus
      had RAW table fallback (gen quota was also spent), confounding the
      financial-statement cases. Re-run both embedders over a corpus WITH proper
      table summaries, once quota resets, to attribute quality fairly.

---

## P2 — Correctness follow-ups

- [x] **Table-HTML cleanup uses a parser now (2026-06-15).** `_clean_table_html`
      reimplemented with BeautifulSoup(lxml) — robust on nested tables (outermost
      only), `<th>`, colspans; never throws (returns input unchanged on parse
      failure). Same signature; 22 tests in `test_table_clean.py`.
- [x] **Store `period_of_report` as a metadata column** — DONE (round 7), with an
      injection-safe date filter.
- [x] **Re-ingest the stale AAPL rows** — DONE (refreshed to local-bge-large;
      36→52/94 chunks).
- [ ] **Remove/justify unused `index_offset`** param in `_elements_to_chunks`.

---

## P3 — Ops / infra robustness

- [x] **Rebuilt the venv on Python 3.14** (round 5) — invoke `./.venv/bin/python`.
- [ ] **Lock dependencies** (`uv` or `pip-tools`) for reproducible installs.
- [ ] **Cross-process durability.** `_ingest_tasks` is in-memory per-worker.
      Only matters if this goes multi-worker — then move to Redis/Celery.
- [x] **Frontend bundle size FIXED (2026-06-15).** recharts + react-markdown
      lazy-loaded (`React.lazy` + `manualChunks`); main JS chunk 731 kB → 78 kB
      (gzip 224 → 26 kB), >500 kB warning gone.

---

## P3 — Future features

- [ ] Bulk 10-Q ingestion (multiple quarters in one action).
- [ ] **Watchlist / portfolio view** — a saved set of tickers with a cross-ticker
      dashboard (comparison charts exist; saved watchlist + recurring-use surface
      does not). The highest-value net-new feature.
- [x] **Form 4 / 13F trackers** (insider + institutional) — DONE (round 7), plus
      the smart-money "which superinvestors hold X" tracker.
- [ ] Catalysts / earnings-date awareness, alerts (not started).

---

## Done recently (prune once it's old news)

### Round 5 (2026-06-15) — ingestion latency + agentic groundwork
- [x] **Rebuilt the venv on Python 3.14** (`.venv`), reinstalled all deps, 121
      backend tests green. Clears the long-standing P3 broken-by-move venv
      blocker. Invoke `./.venv/bin/python -m pytest backend/tests`.
- [x] **PATH A (HTML) and PATH B (XBRL) now run concurrently** in
      `ingest_filing` (was sequential). Both share the single resolved filing
      object; PATH A fatal, PATH B best-effort. (`backend/pipeline/ingest.py`)
- [x] **Batched table summarization** — the dominant ingestion cost. Tables are
      grouped `table_summary_batch_size` (default 6) per LLM call, batches run
      in parallel under the token bucket (one token per batch). Robust
      delimiter parse with a per-table fallback on count mismatch
      (`summarize_tables` in `table_summarizer.py`). **Measured ~45× faster**
      on AAPL 10-K (86.5s → 1.9s, 31 calls → 6) at a simulated 0.8s/call; same
      94 chunks. New config knobs: `table_summary_rpm`,
      `table_summary_concurrency`, `table_summary_batch_size`.
- [x] **Live ingest progress** — `ingest_filing(on_progress=…)` emits stage
      events (resolving→fetching→parsing→summarizing_tables→embedding→storing→
      done); `IngestTask` surfaces `stage`/`detail` via `/ingest/status`.
- [x] **Agentic core (`backend/agent/`).** Two standout behaviours beyond plain
      RAG, wired into `_chat_stream`:
      (1) **Corpus autonomy** — `plan_auto_ingest` detects when a query names a
      ticker the retrieval didn't surface and the chat auto-ingests that filing
      from EDGAR mid-answer, then re-searches (emits `agent_step` SSE events).
      (2) **Self-verification** — `verify_answer` runs a critic pass auditing the
      answer's claims/numbers against the retrieved sources (emits a
      `verification` SSE event). Both gated by config (`enable_auto_ingest`,
      `enable_self_verification`); decision logic is pure + unit-tested.
      New SSE event types: `agent_step`, `verification` (see `/chat` docstring).
- [x] **Eval harness scaffolding** — see the P2 RAG-quality section above.
### Round 6 (2026-06-15) — ReAct agent, local embeddings, parser, FE polish
- [x] **Multi-tool ReAct loop** (`backend/agent/react.py`) — model-driven
      search/ingest/list_corpus/answer loop, default on (`enable_react_agent`),
      reusing the synthesis + verification tail. Live-validated against
      gemini-2.5-flash (drove search→answer to a cited multi-year chart).
- [x] **Local offline embeddings** (`local-bge-large`, default) — removes the
      embedding key/quota dependency.
- [x] **Table-HTML cleanup → BeautifulSoup**; **eval set → 24 cases + flexible
      section matching**; **FE: responsive + a11y + bundle 731→78 kB**.
- [x] **Native Gemini function-calling for ReAct (opt-in)** — `GeminiToolSession`
      in `llm.py`, `ReactAgent(native=True)`; `agent_native_tools` (default OFF).
      Live-validated round-trip; convergence guard stops on no-new-evidence.
      Text-ReAct stays the default until native stop-efficiency is fully tuned.
- [x] **Multi-series comparison charts** (FE) + synthesis emits the multi-series
      `<chart>` spec (type bar/line/area). Comparison is now functional E2E: the
      ReAct loop auto-ingests each named company, then synthesizes a multi-series
      chart.
### Round 7 (2026-06-15) — holdings trackers, period_of_report, ops, hosting doc
- [x] **Form 4 insider + 13F holdings trackers** (`backend/holdings/`) — EDGAR-only,
      no key/quota. Per-ticker insider buy/sell (live-verified AAPL) + per-fund
      13F top holdings (verified BRK-B). ReAct tools (results = citable synthetic
      sources) + `GET /insiders/{ticker}` `/institutions/{fund}` + insider sidebar
      panel.
- [x] **Smart-money tracker** (`superinvestors.py`) — solves "which funds hold
      ticker X" via a CURATED superinvestor universe (`funds.json`, 11 verified
      CIKs, editable): `refresh()` pulls each fund's latest+prior 13F → local
      ticker-keyed index with Q/Q change tags (new/added/trimmed/exited);
      `funds_holding(ticker)` queries it instantly. ReAct tool + `GET
      /smart-money/{ticker}` + `POST /smart-money/refresh` + sidebar panel.
      Live-verified: 11 funds / 319 positions in ~4s (AAPL→Buffett 22%, META→Burry
      exited, GOOGL→Buffett added). NOTE: curated/notable funds, not all ~5k
      filers (EDGAR has no global reverse-index) — and that's the higher-signal set.
- [x] **`period_of_report` metadata column** + injection-safe date filter.
- [x] **Bounded ingest task store** (`_MAX_INGEST_TASKS`, evicts oldest finished).
- [x] **Hosting/AI brainstorm** → `docs/HOSTING_AND_AI_OPTIONS.md` (TL;DR: pain is
      rate limits not $; a paid Gemini key is pennies; when public, split deploy —
      static FE on Cloudflare Pages, FastAPI+LanceDB on Fly.io/Railway).
- [ ] **NEXT options:** (a) make native FC the default once stop-efficiency tuned;
      (b) durable cross-process task store (Redis) only if multi-worker; (c) paid
      Gemini key / Bedrock route to escape free-tier caps.

### UX audit (2026-06-15) — see `docs/UX_AUDIT.md`
Headline: we built an autonomous analyst but the UI framed it as "ingest then
query" — the gap is DISCOVERABILITY, not capability.
- [x] P0: reframed empty-state copy to "ask about any company, I'll fetch it";
      capability-showcasing suggested prompts (auto-fetch/compare/smart-money/
      insiders); wider composer placeholder.
- [ ] Key insider/smart-money panels to the LAST-DISCUSSED ticker, not only a
      focused filing (discovered without ingesting first).
- [ ] De-emphasize manual Ingest (auto-ingest is the front door) + "you can just
      ask" hint; tooltip explaining the verification badge.
- [x] Chat-dominant default split + chat persistence (localStorage).
- [x] **Visual audit + 3-theme system** (see `docs/VISUAL_AUDIT.md`): contrast
      bump, mobile header-overflow fix, prompts-below-fold fix, insider-row
      restructure; Study (default) + Modern-Dark + Modern-Light (electric blue),
      toggle in the chat header, persisted. Verified via screenshots in all 3.
- [ ] Remaining UX: key panels to last-discussed ticker is DONE; still open —
      "you can just ask" hint near (now-removed) ingest is moot; consider a
      collapsible source panel.

### TEST-LATER (deferred on free-tier quota — DO THIS)
- [ ] Full live ReAct run exercising the new insider/13F tools end-to-end (the
      data fetch is verified; the agent-calls-tool→synthesize path needs gen
      quota). Re-ingest with period_of_report populated once quota resets.
- [ ] Re-run the clean embedding A/B (local-bge-large vs gemini-embedding-001)
      over a corpus WITH proper table summaries, once daily gen quota resets.
- [ ] Full live ReAct exercise that triggers a real auto-ingest end-to-end
      (blocked today by the flash-lite per-DAY generation cap + embedding/min cap).
- [x] Frontend visual QA in a real browser — DONE: screenshotted all 3 themes
      (desktop + populated panels + mobile) during the visual audit.

### Round 4 (2026-06-09) — visual redesign: "The Analyst's Study"
- [x] **Root-cause spacing bug:** an un-layered `* { margin:0; padding:0 }`
      reset in `index.css` out-cascaded Tailwind v4's `@layer utilities`,
      zeroing **every** padding/margin utility app-wide. Removed (preflight
      already resets). This alone changed how the whole app renders.
- [x] Full retheme (token values only — semantic names stable): racing-green
      ink surfaces, brass-gold foil accent, ivory type; Gloock display +
      Hanken Grotesk UI + Spline Sans Mono figures (Newsreader kept for prose);
      grain + guilloche + lamp-glow body atmosphere.
- [x] Signature: **sources render as ivory paper "exhibits"** (`.vr-paper`,
      print-mode SEC table styles); gold-foil primary buttons with hover sheen
      (`.vr-foil`); certificate double-rules; dotted ledger leaders in sidebar.
- [x] UX: empty-desk hero with clickable suggested-prompt slips (fill the
      composer); engraved seal masthead + EDGAR-live ledger footer; exhibit
      cover-line headers; composer hint row; reading-view modal chrome.
- [x] Verified live via Playwright screenshots (empty, conversation, chart,
      paper exhibit, modal) against a dev-only stubbed-LLM server; build +
      9 Vitest + 112 pytest all green.

### Round 3 (2026-06-09) — audit: config drift, error surfacing, citation UX
- [x] **Fixed fatal config drift:** `.env` pointed at `gemini-2.0-flash`
      (shut down upstream), `gemini-2.5-pro-preview-03-25` (retired preview),
      and `text-embedding-004` (768-dim) against a 3072-dim LanceDB table.
      Now `gemini-3.1-flash-lite` / `gemini-3.5-flash` / `gemini-embedding-001`
      (verified against live Google docs); `.env.example` + `config.py` aligned.
- [x] Unknown embedding models now **raise** instead of silently defaulting to
      768 (`embedder.py`); `get_table()` validates the table's vector dim
      against `EMBEDDING_DIM` and fails fast with a re-ingest hint (`store.py`).
- [x] **Synthesis errors surface to the client** as SSE `error` events — a
      producer-thread exception previously ended the stream silently with an
      empty answer (`main.py`).
- [x] RAG: sliding-window **chunk overlap** (250 chars, word-aligned, intra-
      section only) in `_merge_text_elements`; **row-aware table truncation**
      (`</tr>` boundary) in `_format_sources`.
- [x] Frontend: `X-API-Key` header via `VITE_API_KEY` (`api.ts`); dead nav
      items removed (Query History / Settings / Sign Out); SourcePanel Search
      icon cut, **Download + Expand wired** (JSON export, Modal); **clickable
      citation pills** focus the matching source (state lifted to `App.tsx`);
      `--color-amber-200` token added.
- [x] Deprecations: `table_names()` → `list_tables().tables`; pydantic
      class-`Config` → `SettingsConfigDict`.
- [x] Tests 99 → **112** (synthesis-error surfacing, truncation, overlap,
      dim registry, dim-mismatch fail-fast).

### Round 2 and earlier (prune soon)
- [x] Multi-turn chat; hybrid retrieval (RRF + BM25-lite) + MMR; history-aware
      reformulation; security (filters/auth/rate-limit/CORS); XBRL revival;
      quarter inference; parallel table summarization; cached LanceDB
      connection; Tailwind v4 design system + ui/ primitives + Vitest;
      bounded SSE + disconnect handling; request-id logging.
