# Design — Structured Fact Base + Valuation Engine

> **Status: DESIGN / proposal (not built).** This is the spec for Mosaic's next
> phase: shifting from "re-read filings on every query" to "structure the
> unstructured **once** at ingest, then retrieve/compute cheaply." It's the
> architecture that makes Mosaic a *valuation* product rather than a filing
> chatbot, and it's cheaper to run. No code has been written against this yet.

## 1. Why (the thesis)

Today Mosaic is **re-read-every-query**: at ingest we chunk/embed/summarize, but
the actual *numbers* live in prose + table-summary text, so each query sends
retrieved chunks to the expensive synthesis model, which **re-derives** the
figures from text every time. That is (a) expensive, (b) slow, and (c)
hallucination-prone on exactly the thing that matters most — the numbers.

The redesign, in one line: **extract a normalized financial fact base once at
ingest (a one-time cost, mostly deterministic from XBRL), then make query-time a
cheap retrieval + deterministic math.** This is the same pattern a medical agent
uses — pre-structure the record so "chest pain" is a lookup, not a re-parse.

It does three things at once:
1. **Cost collapses** — extraction is paid once per filing, amortized over every
   future query and every automated alert; query-time is a cheap model + math.
2. **Trust goes up** — core numbers are deterministic + traceable to the XBRL
   tag, not an LLM guess. This is the audit story no base chatbot has.
3. **It unlocks valuation** — valuation needs reliable, repeatable, multi-period,
   multi-company numbers; that's exactly what a structured base provides and what
   a stateless chatbot is worst at.

Insider / 13F / superinvestor activity becomes a **supporting signal** into a
thesis, not the headline.

## 2. Architecture: three layers

### Layer 1 — Structured Financial Fact Base (new, the spine)
A normalized, queryable store of financial line items per `(company, period)`,
built once at ingest. This is **relational/numeric**, not vectors — so it lives
in an embedded SQL store alongside LanceDB, **not** in LanceDB.

- **Storage:** **SQLite** to start (stdlib, zero new dependency, on-disk — fits
  the local/$0 ethos). Upgrade path: **DuckDB** if cross-company analytical
  queries (percentiles, peer comps over many tickers) get heavy. Both are
  embedded; no server.
- **Schema (sketch):**
  - `companies(cik, ticker, name, sic, fiscal_year_end)`
  - `filings(filing_id, cik, form_type, filing_date, period_of_report,
    fiscal_year, fiscal_quarter, accession_no, source_url)`
  - `financial_facts(filing_id, statement, line_item, period_start, period_end,
    value, unit, source_concept, source_method, confidence)` — the core. One row
    per normalized line item per period.
  - `segments(filing_id, segment_name, revenue, operating_income, period_*)`
  - *(optional)* `market_data(ticker, date, price, shares)` — for price-based
    multiples; **not** in EDGAR (see risks).
- **Canonical line-item taxonomy** — the crux of cross-company comparability. A
  maintained map from messy XBRL concepts → a controlled vocabulary, e.g.
  `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
  → `revenue`; `us-gaap:NetIncomeLoss` → `net_income`. Canonical keys:
  `revenue, cost_of_revenue, gross_profit, operating_income, net_income, ebitda,
  total_assets, total_liabilities, total_debt, cash_and_equivalents,
  shares_diluted, operating_cash_flow, capex, free_cash_flow, …`.
- **Provenance on every fact** — `source_method ∈ {xbrl, llm, computed}`,
  `source_concept` (the tag), `filing_id`. Full audit trail = the trust moat.

### Layer 2 — Unstructured RAG (existing, role narrows)
Keep `sec_chunks` for the **qualitative** parts — risk factors, MD&A narrative,
business/moat description, management tone. Semantic search + the synthesis model
genuinely add value here (judgment, nuance) and re-reading is fine because it's
not arithmetic. **Numbers stop coming from this layer.**

### Layer 3 — Valuation Engine (new, deterministic + transparent)
A pure-Python module computing, from the fact base (no LLM in the math):
- **Ratios & trends:** margins, YoY/CAGR growth, ROIC/ROE, leverage
  (net debt / EBITDA), FCF margin/yield, working-capital trends.
- **Multiples** (need price): P/E, EV/EBITDA, P/FCF, P/S — vs history and peers.
- **DCF scaffold:** project FCF from historical growth + **explicit, user-
  overridable** assumptions (growth, margin, WACC, terminal); output an intrinsic-
  value *range*, not a point.
- **Comps:** same metrics across a peer set; percentile the target.
Metrics are **computed on read** from facts (facts are the single source of
truth) so they can never drift. The LLM **narrates** these; it does not compute
them.

## 3. Extraction: XBRL-first, LLM-assisted for the gaps

- **~85–90% deterministic from XBRL** (`edgartools` `income_statement()` /
  `balance_sheet()` / `cashflow_statement()` — already fetched today as the
  "best-effort PATH B"; this promotes it to first-class). Map concepts → canonical
  keys via the taxonomy.
- **LLM-assisted only for the gaps:** items missing/oddly-tagged in XBRL, segment
  breakdowns that live in tables/footnotes, restatement reconciliation. The LLM
  returns a **specific number + citation as structured JSON, once at ingest** (a
  cheap model, or fold into the existing table-summary pass) — never re-derived
  per query. These facts carry `source_method=llm` + lower confidence.
- **Validation (deterministic sanity checks):** `gross_profit ≈ revenue −
  cost_of_revenue`; `assets ≈ liabilities + equity`; `FCF ≈ OCF − capex`.
  Mismatches flag the fact (lower confidence / surface for review) and catch
  extraction errors before they reach a valuation.

## 4. Query-time: the cheap/expensive split

New ReAct tools backed by the structured store (return structured data, not prose):
- `get_financials(ticker, metrics, periods)` — deterministic lookup.
- `compute_valuation(ticker, assumptions?)` — runs the engine.
- `compare_metrics(tickers, metric)` — cross-company.

Routing of work:
- **Most queries → cheap model.** "AAPL FCF-margin trend?" = structured lookup +
  math, cheap model narrates the result. No filing re-read.
- **Expensive synthesis model reserved** for genuine thesis work — combining
  numbers + narrative into a bull/bear case, "what would change my mind" — and
  even then it reads *pre-structured facts* + a few targeted narrative chunks, not
  raw filings.

Cost shape: today every query ≈ one expensive synthesis call re-reading ~15
chunks. After: ingest pays a one-time extraction cost; a typical metric/valuation
query is cheap-model + deterministic math (≈ free locally); only thesis-level
queries hit the big model. **This is what makes always-on alerting economically
viable** — thousands of automated checks are pure deterministic computation.

## 5. Layer 4 — Watchlist + Alerts (the always-on surface)

- **Watchlist:** saved tickers; on a new-filing trigger or schedule, run
  deterministic checks over the fact base + valuation engine.
- **Alert rules (deterministic):** metric thresholds (leverage > X, FCF margin
  down N quarters), valuation triggers (intrinsic-value gap, multiple vs
  history/peers), events (new 10-K/10-Q/8-K, insider cluster buy, superinvestor
  opens/exits a position).
- The LLM only writes the human-readable "**here's what changed in the thesis**"
  over the structured deltas. Cheap, and impossible to do consistently by
  re-prompting a chatbot.

## 6. Mapping to the codebase (extension, not rewrite)

- `pipeline/ingest.py` — add a structured-extraction step after XBRL fetch
  (PATH B promoted from best-effort to first-class), writing to the new store.
- `backend/facts/` (new) — SQLite schema, canonical taxonomy map, extractor
  (xbrl + llm-gap), validator, typed query API.
- `backend/valuation/` (new) — pure deterministic metrics + DCF + comps.
- `agent/react.py` — the three new structured tools above.
- Synthesis — prefer structured facts, cite them, reserve the big model.
- `backend/watchlist/` (new) + endpoints + a scheduler (or trigger on ingest).
- Models — the existing `FAST_MODEL` / `AGENT_MODEL` / `SYNTHESIS_MODEL` split
  already supports cheap-retrieval vs. expensive-synthesis.

## 7. Phasing

1. **Fact base + XBRL extractor + taxonomy + provenance + validation** +
   `get_financials`. Foundational; immediately improves number reliability and
   cuts per-query cost.
2. **Valuation engine** (ratios / trends / comps / DCF) + `compute_valuation` +
   transparent, user-driven assumptions.
3. **Watchlist + alert rules + scheduler**; insider/superinvestor become signals.
4. **Thesis synthesis** (bull/bear, "what would change my mind") over structured
   facts + targeted narrative.

## 8. Risks / honest caveats

- **XBRL normalization is the hard 20%** — custom/inconsistent tags, restatements,
  segment definitions that vary by company. Mitigate with the validation
  identities, confidence scoring, provenance, and a concept map that grows over
  time. Budget real effort here; it's where comparability is won or lost.
- **Price/market data is not in EDGAR.** Multiples and any market-relative
  valuation need a price source (e.g. `yfinance` free tier, or a paid feed).
  Pure-fundamental metrics don't; gate the price-dependent ones on that source.
- **Valuation is judgment, not an oracle.** Ship a *transparent valuation
  workbench* — assumptions explicit and user-driven, intrinsic value as a range,
  "show your work." Never "the AI says buy."
- **Stay on the analysis side of the advice line** — build the case and the
  numbers; the user decides.
- **Biggest build yet** — but it's an extension (XBRL ingest already exists), and
  it's the part nobody gets from a base model. Phase it.
