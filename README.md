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
| [docs/blueprints/](docs/blueprints/) | Original architecture blueprints + future-feature concepts (portfolio analyzer, insider/13F trackers) |

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
./.venv/bin/python -m pytest backend/tests   # backend (112 passing)
                              # (invoke the venv python directly — see docs/TODO.md P3)
cd frontend && npm test       # frontend (Vitest)
```

## Stack

- **Backend:** FastAPI, LanceDB (local vector store), `edgartools` (SEC EDGAR),
  `unstructured` (HTML parsing), provider-agnostic LLM/embedding routing
  (Gemini / Claude / OpenAI, selected by model-name prefix in `.env`).
- **Retrieval:** vector search with metadata pre-filtering, hybrid RRF + lexical
  fusion, MMR diversification, and history-aware query reformulation.
- **Frontend:** React 18 + Vite + TypeScript, Tailwind v4 design system,
  Recharts, SSE streaming with abortable requests.
- **Security:** injection-safe filter construction, optional API-key auth, per-IP
  rate limiting, locked CORS.

> **Note:** The POC defaults to a $0 Google/Gemini stack. A valid `GOOGLE_API_KEY`
> is required for ingestion (embeddings) and chat (synthesis); EDGAR fetch and XBRL
> parsing work without it. See [docs/TODO.md](docs/TODO.md) for current blockers.
