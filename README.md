# Value Investing RAG

A local, multi-provider RAG pipeline for querying SEC filings (10-Ks, 10-Qs) with LLM-powered analysis.

## Docs

| File | Description |
|---|---|
| [docs/reference/BACKEND.md](docs/reference/BACKEND.md) | Full backend reference — setup, architecture, API, config |
| [docs/blueprints/ValueInvestingRAG.md](docs/blueprints/ValueInvestingRAG.md) | Original RAG architecture blueprint |
| [docs/blueprints/ValueInvestingUI.md](docs/blueprints/ValueInvestingUI.md) | Frontend/UI architecture blueprint |
| [docs/blueprints/PortfolioAnalysis.md](docs/blueprints/PortfolioAnalysis.md) | Portfolio impact analyzer concept (future work) |
| [docs/reference/FRONTEND_IMPLEMENTATION.md](docs/reference/FRONTEND_IMPLEMENTATION.md) | Full frontend reference (Next.js/React) |

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

### Frontend (Visual Prototype & Phase 2)
- [ ] **State Management:** Integrate Vercel AI SDK (`useChat`) to replace mock message state.
- [ ] **Streaming Indicators:** Connect `AgentState.tsx` to backend SSE/WebSocket for live "thought process" updates.
- [ ] **Generative UI:** Finalize JSON schemas for tool-calling (e.g., `FinancialChart`, `MetricGrid`).
- [ ] **Citation Interactivity:** Implement "click-to-scroll" from chat citations to the `SourcePanel` document viewer.
- [ ] **SEC Filing Parser:** Add a utility to convert raw SEC HTML/XBRL into the clean, readable format used in `SourcePanel.tsx`.
- [ ] **Responsive Refinement:** Ensure the resizable split-pane handles edge cases on smaller screens.

### Backend (Claude)
- [ ] End-to-end test with a real ticker (ingest AAPL 10-K, run a query)
- [ ] Verify `unstructured` correctly separates tables from narrative text on SEC HTML
- [ ] Tune `_MIN_CHUNK_LENGTH` — 100 chars may be too aggressive or too loose
- [ ] Add a `GET /filings` endpoint to list what's already been ingested
- [ ] Handle 10-Q quarter inference more robustly (current logic has overlapping month ranges)
- [ ] Background task queue for `/ingest` (currently blocks the request for minutes)

### RAG Quality
- [ ] Evaluate retrieval precision — are the right chunks coming back for test queries?
- [ ] Experiment with chunk size (currently element-level; may need sentence-window or parent-doc retrieval)
- [ ] Test `claude-sonnet-4-6` vs `gemini-2.5-pro` for synthesis quality on financial queries
- [ ] Add re-ranking step (cross-encoder) before passing chunks to synthesis LLM

### Infrastructure
- [ ] Add `.gitignore` entries for `data/lancedb/` and `.env`
- [ ] Upgrade Python to 3.11+ (3.9 is EOL, Google SDKs warn on every import)
- [ ] Lock down CORS (`allow_origins=["*"]` is fine for local dev only)
- [ ] Add structured logging

### Future / Portfolio Analyzer
- [ ] Merge `PortfolioAnalysis.md` concept into this repo
- [ ] LangGraph DAG for supply chain risk extraction
- [ ] Neo4j knowledge graph for portfolio intersection queries
