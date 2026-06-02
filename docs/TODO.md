# TODO — Value Investing RAG

Single source of truth for outstanding work. Prioritized, with file pointers.
Companion to `docs/PROJECT_STATUS_AND_ROADMAP.md` (background, architecture
invariants, what's already done). **Keep this file updated** — check items off,
add new ones, move things between sections as priorities shift.

Last reconciled against code: 2026-06-02 (after round 2: RAG quality + ops + design system).

Status legend: `[ ]` not started · `[~]` partial · `[x]` done (leave briefly for context, then prune)

---

## P0 — Blockers (nothing real works end-to-end until these are cleared)

- [ ] **Refresh `GOOGLE_API_KEY` in `.env`.** Current key is invalid → every Gemini
      call fails (embeddings during ingest, synthesis during chat, query
      reformulation). This is why the app "looks unfinished": you cannot ingest a
      filing, so the sidebar shows "No filings ingested yet" and the chat/source
      panels sit in their empty states. EDGAR fetch + XBRL parse still work without it.
- [ ] **Live end-to-end smoke test** once the key is valid: ingest one filing
      (e.g. AAPL 10-K) → confirm chunks land in LanceDB → ask a question → confirm
      streaming answer + sources + a chart. This is the only thing none of the 99
      backend tests can cover (they mock the LLM/embeddings).

---

## P1 — "Finish the frontend" (the visible polish gaps)

The Tailwind v4 design system + `ui/` primitives are in place and the build/lint/
Vitest are green. What remains is dead UI and missing wiring that make it feel
incomplete:

- [ ] **Wire or remove dead sidebar nav items.** `Sidebar.tsx:86-87,158-159`:
      "Query History", "Settings", "Sign Out" render but have no `onClick`. Either
      implement them or cut them. ("Analysis Lab" is the only live one.)
- [ ] **Wire or remove SourcePanel toolbar icons.** `SourcePanel.tsx:49-54`:
      Search / Download / Maximize2 buttons are decorative. Cheap wins: Download
      (export the raw source payload), Maximize (expand the source in a Modal).
      Search needs more thought — cut it if not building it.
- [ ] **Clickable citations.** Clicking `[1]` in an answer (or a source pill in
      `Message.tsx`) should focus/scroll the matching source in `SourcePanel`.
      Requires lifting source/active-index state to `App.tsx` or a context.
- [ ] **Define missing token `--color-amber-200`** (referenced as `text-amber-200`
      in components but not in the `@theme` block of `index.css`) — currently renders
      unstyled/inherited. Either add the token or change the references to `amber-300`.
- [ ] **Empty/loading/error states pass.** Now that data can flow (post-P0), review
      the real states: first-run (no filings), mid-ingest, chat before first message,
      retrieval-returned-nothing, and backend-down. Make sure each looks intentional.
- [ ] **Accessibility sweep.** Filing rows in `Sidebar.tsx:104` are `role="button"`
      divs (keyboard handler exists — good); audit the rest for real `<button>`s,
      `aria-label`s, and an `ErrorBoundary` at the App root.
- [ ] **Responsive layout.** Desktop-only today (fixed sidebar width, %-based split
      pane in `App.tsx`). Decide whether mobile/tablet matters; if so, collapse the
      sidebar + stack panels under a breakpoint.

---

## P1 — Auth follow-through

- [ ] **Send `X-API-Key` from the frontend.** `frontend/src/api.ts:36,75` only set
      `Content-Type`. When `settings.api_key` is configured server-side, `/chat`,
      `/ingest`, `/retrieve` will 401. Add the header (from an env var / settings UI)
      before enabling auth in any deployed environment. (Fine while auth is disabled
      by default for local dev.)

---

## P2 — RAG quality (improve answer quality)

Hybrid retrieval (RRF + BM25-lite), MMR diversification, and history-aware query
reformulation already shipped (`backend/retrieval/`). Remaining:

- [ ] **Evaluation harness.** We added hybrid + MMR + reformulation but have NOT
      measured whether they actually improve answers on real queries. Build a small
      eval set (question → expected filing/section) and an offline scorer so future
      retrieval changes are data-driven, not vibes. Requires a valid API key.
- [ ] **Chunk overlap.** `_merge_text_elements` in `backend/pipeline/ingest.py` uses
      a hard ~2500-char cut with no overlap → facts spanning a boundary get split.
      Add sliding-window overlap.
- [ ] **Row-aware source truncation.** `_format_sources` in `backend/api/main.py`
      does `raw_payload[:2000]`, which can cut a table mid-row before it reaches the
      LLM. Truncate on row boundaries for table chunks.
- [ ] **Tune reformulation/hybrid/MMR params** against the eval harness (overfetch
      factor, `mmr_lambda`, RRF `k`, the `should_reformulate` heuristic thresholds).

---

## P2 — Correctness follow-ups (from the backend audit)

- [ ] **Replace regex table-HTML cleanup with a parser.** `_clean_table_html` /
      `_add_thead` in `backend/pipeline/ingest.py` are fragile on nested tables,
      `<th>`, colspans, and multi-row headers. Move to `lxml`/`bs4` (already
      transitive deps via `unstructured`), OR lean on the now-working XBRL path for
      core statements and only keep HTML for narrative.
- [ ] **Store `period_of_report` as a metadata column.** `filing_quarter` is a
      *calendar* quarter, which differs from the *fiscal* quarter for off-cycle
      filers (e.g. AAPL). A real period-end date column enables unambiguous date
      filtering. Requires a schema change + re-ingest of existing rows.
- [ ] **Re-ingest the stale AAPL row.** The one pre-existing row keeps its old
      (buggy) quarter label until re-ingested; new ingests are already correct.
- [ ] **Remove/justify unused `index_offset`** param in `_elements_to_chunks`.

---

## P3 — Ops / infra robustness

Bounded SSE + disconnect handling, typed ingest state, and request-id logging
already shipped (`backend/api/`). Remaining:

- [ ] **Cross-process durability.** `_ingest_tasks` is in-memory per-worker (lost on
      restart, not shared across workers). Only matters if this goes multi-worker —
      then move to Redis/Celery.
- [ ] **Python 3.9 → 3.11+.** 3.9 is EOL. Unblocks modern syntax and removes a class
      of deprecation noise.
- [ ] **Lock dependencies** (`uv` or `pip-tools`) for reproducible installs.
- [ ] **Clear benign deprecation warnings:** LanceDB `table_names()` → `list_tables()`
      (`backend/pipeline/store.py`); pydantic class-`Config` → `ConfigDict`
      (`backend/config.py`).
- [ ] **Frontend bundle size.** `npm run build` warns the JS chunk >500 kB
      (recharts + react-markdown). Code-split / lazy-load the chart + markdown
      renderer if load time matters.

---

## P3 — Future features (blueprints exist in the audit; not started)

- [ ] Bulk 10-Q ingestion (multiple quarters in one action).
- [ ] Portfolio analyzer (cross-filing / cross-ticker comparison views).
- [ ] Form 4 / 13F trackers (insider + institutional holdings).

---

## Done recently (prune once it's old news)

- [x] Multi-turn chat (synthesis + history-aware retrieval reformulation).
- [x] Security: injection-safe filters, optional API-key auth, per-IP rate limiting, CORS lock.
- [x] Correctness: 10-Q quarter inference, XBRL revival, `/filings` error surfacing.
- [x] Perf: parallel table summarization, cached LanceDB connection + index.
- [x] Frontend: DOMPurify XSS fix, abortable streaming, Tailwind v4 design system + `ui/` primitives + Vitest.
- [x] Ops: bounded SSE + disconnect handling, typed ingest state, request-id logging.
- [x] RAG: hybrid retrieval (RRF + BM25-lite), MMR diversification.
