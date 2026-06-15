# TODO — Value Investing RAG

Single source of truth for outstanding work. Prioritized, with file pointers.
Companion to `docs/PROJECT_STATUS_AND_ROADMAP.md` (background, architecture
invariants, what's already done). **Keep this file updated** — check items off,
add new ones, move things between sections as priorities shift.

Last reconciled against code: 2026-06-09 (after round 3: config-drift fixes,
synthesis-error surfacing, citation UX, chunk overlap, deprecation cleanup).

Status legend: `[ ]` not started · `[~]` partial · `[x]` done (leave briefly for context, then prune)

---

## P0 — Blockers (nothing real works end-to-end until these are cleared)

- [ ] **Set a real `GOOGLE_API_KEY` in `.env`.** All three provider keys in
      `.env` are placeholders — no LLM/embedding call can succeed. Get a free
      key at https://aistudio.google.com/app/apikey. Everything else in the
      stale-config cluster was fixed 2026-06-09 (model names, embedding dim) —
      the key is the only remaining blocker. EDGAR fetch + XBRL parse work
      without it.
- [ ] **Live end-to-end smoke test** once the key is valid: ingest one filing
      (e.g. AAPL 10-K) → confirm chunks land in LanceDB → ask a question →
      confirm streaming answer + sources + a chart. The 112 backend tests mock
      all LLM/embedding calls, so this is the only unverified path.
      Note: `gemini-3.5-flash` / `gemini-3.1-flash-lite` (set 2026-06-09 from
      live Google docs) should be re-checked against
      https://ai.google.dev/gemini-api/docs/models if this sits for months —
      stale model names were a silent 404 source before.

---

## P1 — "Finish the frontend" (the visible polish gaps)

- [ ] **Empty/loading/error states pass.** Now that synthesis errors are
      surfaced (not silently swallowed), review the real states post-P0:
      first-run (no filings), mid-ingest, retrieval-returned-nothing,
      backend-down, synthesis-error. Make sure each looks intentional.
- [ ] **Accessibility sweep.** Filing rows in `Sidebar.tsx` are `role="button"`
      divs (keyboard handler exists — good); audit the rest for `aria-label`s
      and add an `ErrorBoundary` at the App root.
- [ ] **Responsive layout.** Desktop-only today (fixed sidebar width, %-based
      split pane in `App.tsx`). Decide whether mobile/tablet matters; if so,
      collapse the sidebar + stack panels under a breakpoint.
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
      without a key. REMAINING: ingest the referenced filings + run live to get
      real baseline numbers, then expand the set beyond AAPL.
- [ ] **Tune reformulation/hybrid/MMR/overlap params** against the eval harness
      (overfetch factor, `mmr_lambda`, RRF `k`, `_TEXT_CHUNK_OVERLAP`,
      `should_reformulate` thresholds).
- [ ] **Consider local embeddings** (e.g. `fastembed`, ONNX, no torch) as a
      `local-*` route in `embedder.py`: would make ingest + retrieval work with
      zero API keys (only synthesis would need one). Trade-off: weaker
      embeddings than gemini-embedding-001, new dep, and a re-ingest (different
      dim). Do after the Python 3.11 upgrade — onnxruntime has dropped 3.9.

---

## P2 — Correctness follow-ups

- [ ] **Replace regex table-HTML cleanup with a parser.** `_clean_table_html` /
      `_add_thead` in `backend/pipeline/ingest.py` are fragile on nested
      tables, `<th>`, colspans, multi-row headers. Move to `lxml`/`bs4`
      (already transitive deps via `unstructured`), OR lean on the XBRL path
      for core statements and keep HTML only for narrative.
- [ ] **Store `period_of_report` as a metadata column.** `filing_quarter` is a
      *calendar* quarter, which differs from the *fiscal* quarter for off-cycle
      filers (e.g. AAPL). Requires a schema change + re-ingest.
- [ ] **Re-ingest the stale AAPL rows.** The 36 pre-existing rows keep their old
      (buggy) quarter labels until re-ingested; new ingests are correct.
- [ ] **Remove/justify unused `index_offset`** param in `_elements_to_chunks`.

---

## P3 — Ops / infra robustness

- [ ] **Rebuild the venv on Python 3.11+.** Two reasons now: 3.9 is EOL, AND
      the current `.venv` is broken-by-move — `pyvenv.cfg`/`activate` hardcode
      the old `~/Desktop/Code/valueinvesting` path, so `source
      .venv/bin/activate` silently falls through to system Python. Until then,
      invoke `./.venv/bin/python` directly (works fine).
- [ ] **Lock dependencies** (`uv` or `pip-tools`) for reproducible installs.
- [ ] **Cross-process durability.** `_ingest_tasks` is in-memory per-worker.
      Only matters if this goes multi-worker — then move to Redis/Celery.
- [ ] **Frontend bundle size.** `npm run build` warns the JS chunk >500 kB
      (recharts + react-markdown). Code-split / lazy-load the chart + markdown
      renderer if load time matters.

---

## P3 — Future features (blueprints exist; not started)

- [ ] Bulk 10-Q ingestion (multiple quarters in one action).
- [ ] Portfolio analyzer (cross-filing / cross-ticker comparison views).
- [ ] Form 4 / 13F trackers (insider + institutional holdings).

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
- [ ] **NEXT:** full multi-tool ReAct loop (native function-calling) as a v2 of
      the agent — `search`/`ingest`/`compare`/`chart` as real tools the model
      orchestrates, replacing the current fixed pipeline. Frontend agent-step UI +
      verification badge in progress (dispatched). Live e2e once the key is set.

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
