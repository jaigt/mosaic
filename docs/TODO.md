# TODO — Mosaic

Single source of truth for outstanding work. Prioritized, with file pointers.
Companion to [`PROJECT_STATUS_AND_ROADMAP.md`](./PROJECT_STATUS_AND_ROADMAP.md)
(background, architecture invariants, what's done). **Keep this updated** — check
items off, add new ones, move things as priorities shift.

Last reconciled against code: **2026-06-15** (local-first / oMLX round). The repo
is now `github.com/jaigt/mosaic`. Status legend: `[ ]` not started · `[~]` partial
· `[x]` done (kept briefly for context, then pruned).

---

## P0 — Blockers

None. The old P0 — the **free-tier API quota** (embedding per-minute + generation
per-day caps) — is no longer binding: the stack now runs **fully local** by default
(local embeddings + a local oMLX model), so a normal dev/POC session needs no API
key and hits no quota. Cloud keys remain optional fallbacks.

---

## P1 — Visible polish

- [ ] **Friendly ingest/agent error messages.** On an ingest failure the agent
      surfaces the *raw* exception to the user (e.g. a LanceDB schema string).
      Map internal errors to a plain "couldn't fetch X right now — try again"
      while keeping the detail in logs. (`backend/agent/react.py` `_do_ingest`,
      the `ingest_failed` event.)
- [ ] **Empty/loading/error states pass.** Review first-run (no filings),
      mid-ingest, retrieval-empty, backend-down, synthesis-error — make each look
      intentional. (Local synthesis is slow, so the "working…" state matters.)
- [ ] **Inline `[1]` markers clickable.** Source *pills* already focus the
      SourcePanel; making inline `[1]`/`[2]` markers in the markdown clickable
      needs a custom react-markdown text renderer.

---

## P1 — Latency (new, from local-oMLX testing)

- [ ] **Local synthesis is the latency floor (~85–100s/query).** It's dominated
      by the 27B synthesis generation on-device. Options if it bugs us: a smaller
      local synthesis model (quality trade-off), prompt/length trimming, or a
      one-line switch to a cloud-fast synthesis model (cerebras/gemini) when speed
      matters more than offline/$0. The agent loop is already on the faster Gemma
      (`AGENT_MODEL`).
- [ ] **Agent over-search on smaller models.** Gemma occasionally fires several
      near-duplicate searches before answering (capped by `agent_max_steps` + the
      convergence guard, so it's bounded, not broken). Consider a "don't repeat a
      near-identical query" nudge in the ReAct prompt.

---

## P2 — RAG quality

- [~] **Evaluation harness.** Scorer (`backend/eval/metrics.py` — hit@k, MRR) +
      injectable runner (`backend/eval/harness.py`) + seed set (24 cases) DONE and
      unit-tested. REMAINING: refine section labels (allow MD&A for revenue qs),
      re-run with proper table summaries, expand beyond AAPL.
- [ ] **Tune reformulation/hybrid/MMR/overlap params** against the eval harness
      (overfetch factor, `mmr_lambda`, RRF `k`, `_TEXT_CHUNK_OVERLAP`,
      `should_reformulate` thresholds).
- [ ] **Verification model choice.** The critic runs on `FAST_MODEL` (now Gemma).
      Consider running it on the synthesis model for sharper judgment — trades
      latency for fewer misses. (Prompt was just de-stricted; re-evaluate first.)
- [~] **Embedding A/B (local-bge-large vs a hosted embedder)** — largely moot now
      that local is the permanent default; only revisit if retrieval relevance
      looks weak. Deprioritized.

---

## P2 — Correctness follow-ups

- [ ] **Remove/justify unused `index_offset`** param in `_elements_to_chunks`
      (`backend/pipeline/ingest.py`).

---

## P3 — Ops / infra

- [ ] **Lock dependencies** (`uv` or `pip-tools`) for reproducible installs.
- [ ] **Delete merged remote branches** `feat/agentic-latency`,
      `feat/free-llm-providers` on origin (both fully merged into `develop`).
- [ ] **Cross-process durability.** `_ingest_tasks` is in-memory per-worker; only
      matters if this goes multi-worker → Redis/Celery.

---

## P3 — Future features

- [ ] **Watchlist / portfolio view** — a saved set of tickers with a cross-ticker
      dashboard. Comparison charts exist; a saved watchlist + recurring-use
      surface does not. **The highest-value net-new feature** (turns Mosaic from
      "ask about a company" into a daily-use product).
- [ ] **Hosting / deploy** (for showing others) — local oMLX can't be demoed
      remotely. When public: static FE on Cloudflare Pages + FastAPI/LanceDB on a
      small box (Railway/Render/Fly) + a cloud LLM key. See
      [`HOSTING_AND_AI_OPTIONS.md`](./HOSTING_AND_AI_OPTIONS.md).
- [ ] Bulk 10-Q ingestion (multiple quarters in one action).
- [ ] Catalysts / earnings-date awareness + alerts.

---

## Open UX threads (from the audits)

- [ ] De-emphasize/clarify any remaining "ingest-first" framing; consider a
      collapsible source panel. (Manual-ingest UI already removed; panels already
      follow the last-discussed ticker.)

See [`UX_AUDIT.md`](./UX_AUDIT.md) and [`VISUAL_AUDIT.md`](./VISUAL_AUDIT.md) for
the full audit history (most items shipped).

---

## Shipped (condensed — prune as it ages)

### Local-first round (2026-06-15) — provider routing, oMLX, fixes
- [x] **Free OpenAI-compatible provider routing** — `"<provider>/<model>"` prefix
      (cerebras / groq / mistral / ollama / **mlx**) swaps the OpenAI `base_url`;
      escapes Gemini's daily cap with a one-line `.env` change. Transient-429
      retry w/ backoff; SDK `max_retries=0` so our retry governs. (`llm.py`)
- [x] **Fully local on oMLX** (Apple-Silicon mlx server) — synthesis
      `mlx/Qwen3.5-27B-Claude-distill`, fast/agent `mlx/gemma-4-12B`, local
      embeddings. $0, offline, 32k context. oMLX keeps **:8000**; the Mosaic
      backend moved to **:8008** (Vite proxy is `BACKEND_URL`-overridable). oMLX
      API-key supported via `MLX_API_KEY`.
- [x] **`AGENT_MODEL` knob** — drive the ReAct loop with the faster Gemma (~13%
      faster to first token); 27B stays for synthesis.
- [x] **LanceDB schema auto-migration** (`store.py` `_migrate_schema`) — backfills
      columns added after table creation (fixed the `period_of_report` "field does
      not exist" ingest blocker); preserves existing rows.
- [x] **Agent no longer guesses a filing year** — both prompts + tool specs: omit
      `year` → latest filing; set only when the user names one.
- [x] **Verification de-stricted** — critic now ignores unit conversions / rounding
      / derived ratios / formatting and treats sources as a possibly-partial
      excerpt (source window 8k→16k); kills spurious "caveats" on correct answers.
- [x] **UI fixes** — chat avatar `V`→`M`; theme-neutral mosaic-tile **favicon**;
      three-pane **layout overflow fix** (sidebar `shrink-0`, `main` `min-w-0`);
      **theme-aware charts** (recharts colours read CSS vars per theme).
- [x] **Live e2e on local oMLX** — AAPL queries + AAPL/MSFT/GOOGL comparison:
      accurate figures, multi-company chart, `supported` verification, reliable
      Gemma tool-call JSON. 268 backend / 57 frontend tests green.

### Rounds 5–7 (2026-06-15) — agentic core, holdings, perf
- [x] Concurrent PATH A/B ingest + **batched table summarization** (~45× faster).
- [x] **Multi-tool ReAct agent** (search / auto-ingest / list / insider / 13F /
      smart-money) + **self-verification** critic; native Gemini FC opt-in.
- [x] **Local offline embeddings** (`local-bge-large`, default).
- [x] **Holdings trackers** (`backend/holdings/`) — Form 4 insider, 13F, and the
      curated **smart-money superinvestor** index (+ sidebar panels, endpoints).
- [x] `period_of_report` column + injection-safe date filter; bounded ingest-task
      store; eval harness scaffolding; BeautifulSoup table cleanup.
- [x] **Multi-series comparison charts**; hosting/AI brainstorm doc.

### Rounds 1–4 (earlier) — foundation
- [x] Hybrid retrieval (RRF + lexical) + MMR + history-aware reformulation; XBRL
      revival; security (filter allowlist / auth / rate-limit / CORS); multi-turn
      chat; Tailwind v4 design system + Vitest; bounded SSE + disconnect handling;
      the "Analyst's Study" visual redesign + **3-theme system**; UX + visual
      audits; **rebrand ValueRAG → Mosaic**.
