# Mosaic

*Read the filings, not the headlines.*

An autonomous equity-research analyst over SEC filings. Ask about any company and
Mosaic fetches its filings from EDGAR on demand, answers with cited figures and
generative charts, tracks insider (Form 4) and superinvestor (13F) activity, and
self-verifies every number against its sources. FastAPI + LanceDB backend (local
offline embeddings), React + Vite + TypeScript frontend with a multi-tool ReAct
agent, streaming chat, and three themes.

> The name nods to the **mosaic theory** of investing — building a view from many
> lawful primary sources. (Formerly "ValueRAG".)

## Documentation

| File | What's in it |
|---|---|
| [docs/TODO.md](docs/TODO.md) | **Start here** — the live, prioritized backlog |
| [docs/PROJECT_STATUS_AND_ROADMAP.md](docs/PROJECT_STATUS_AND_ROADMAP.md) | Handoff doc: current state, what's done, architecture invariants, environment gotchas |
| [docs/reference/BACKEND.md](docs/reference/BACKEND.md) | Backend reference — structure, API endpoints, data model, LLM routing |
| [docs/reference/FRONTEND_IMPLEMENTATION.md](docs/reference/FRONTEND_IMPLEMENTATION.md) | Frontend reference — components, design system, generative UI |
| [docs/UX_AUDIT.md](docs/UX_AUDIT.md) · [docs/VISUAL_AUDIT.md](docs/VISUAL_AUDIT.md) | UX + visual design audits and fixes (incl. the 3-theme system) |
| [docs/HOSTING_AND_AI_OPTIONS.md](docs/HOSTING_AND_AI_OPTIONS.md) | Hosting + LLM-cost strategy (for later) |
| [docs/blueprints/](docs/blueprints/) | Historical origin blueprints — each banners what's since shipped or diverged (don't treat as current) |

## Quick start

### Backend
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env          # fill in GOOGLE_API_KEY and SEC_USER_AGENT
uvicorn backend.api.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # Vite dev server, proxies /api/* → http://localhost:8000
```

### Tests
```bash
./.venv/bin/python -m pytest backend/tests   # backend (247 passing; venv on Python 3.14)
cd frontend && npm test                       # frontend (Vitest, 57 passing)
```

## Stack

- **Agent:** multi-tool ReAct loop — searches the corpus, **auto-ingests missing
  filings** from EDGAR, pulls insider/13F/smart-money data, and **self-verifies**
  answers against sources. Provider-agnostic LLM routing by model-name prefix
  (Gemini / Claude / OpenAI); native Gemini function-calling opt-in.
- **Backend:** FastAPI, LanceDB (local vector store), `edgartools` (SEC EDGAR),
  `unstructured` (HTML parsing). **Embeddings run locally** (`fastembed`/ONNX
  `bge-large`) by default — no key/quota for ingest or retrieval.
- **Retrieval:** metadata pre-filtered vector search, hybrid RRF + lexical fusion,
  MMR diversification, history-aware reformulation.
- **Frontend:** React 18 + Vite + TypeScript, Tailwind v4, **three themes**
  (Study / Modern-Dark / Modern-Light), Recharts comparison charts, insider +
  smart-money panels, abortable SSE streaming, chat persistence.
- **Security:** injection-safe filter construction, optional API-key auth, per-IP
  rate limiting, locked CORS.

> **Cost:** Embeddings are local ($0). Only **synthesis + the fast model** use an
> API key — the free Gemini tier works but has a per-day generation cap; a paid
> key (pennies/mo) removes it. EDGAR + XBRL need no key. See
> [docs/HOSTING_AND_AI_OPTIONS.md](docs/HOSTING_AND_AI_OPTIONS.md).
