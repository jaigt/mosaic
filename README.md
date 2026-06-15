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
| [docs/VALUATION_ENGINE_DESIGN.md](docs/VALUATION_ENGINE_DESIGN.md) | **Design proposal** — structured fact base + valuation engine (next phase) |
| [docs/blueprints/](docs/blueprints/) | Historical origin blueprints — each banners what's since shipped or diverged (don't treat as current) |

## Quick start

### Backend
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env          # pick your models + set SEC_USER_AGENT (see below)
uvicorn backend.api.main:app --reload
```

Pick a model provider in `.env` (no key needed for the local options):
- **Fully local ($0, offline):** run [oMLX](https://omlx.com)/`mlx_lm` or
  [Ollama](https://ollama.com) and set `mlx/<model>` or `ollama/<model>`. If your
  local server uses port 8000, run the backend on another port (`--port 8008`) —
  the Vite proxy target is overridable via `BACKEND_URL`.
- **Free cloud:** a no-card **Cerebras** key (`cerebras/<model>`, ~1M tok/day).
- **Gemini/Claude/OpenAI:** `gemini-*` / `claude-*` / `gpt-*` (Gemini's free tier
  has a stingy per-day cap).

### Frontend
```bash
cd frontend
npm install
npm run dev                   # Vite dev server, proxies /api/* → http://localhost:8000
```

### Tests
```bash
./.venv/bin/python -m pytest backend/tests   # backend (268 passing; venv on Python 3.14)
cd frontend && npm test                       # frontend (Vitest, 57 passing)
```

## Stack

- **Agent:** multi-tool ReAct loop — searches the corpus, **auto-ingests missing
  filings** from EDGAR, pulls insider/13F/smart-money data, and **self-verifies**
  answers against sources. Provider-agnostic LLM routing by model name —
  prefix families (Gemini / Claude / OpenAI) plus a `<provider>/<model>` form for
  OpenAI-compatible servers (Cerebras / Groq / Mistral and local Ollama / oMLX).
  `AGENT_MODEL` can run the loop on a faster model than synthesis.
- **Backend:** FastAPI, LanceDB (local vector store), `edgartools` (SEC EDGAR),
  `unstructured` (HTML parsing). **Embeddings run locally** (`fastembed`/ONNX
  `bge-large`) by default — no key/quota for ingest or retrieval.
- **Retrieval:** metadata pre-filtered vector search, hybrid RRF + lexical fusion,
  MMR diversification, history-aware reformulation.
- **Frontend:** React 18 + Vite + TypeScript, Tailwind v4, **three themes**
  (Study / Modern-Dark / Modern-Light), **theme-aware** Recharts comparison
  charts, insider + smart-money panels, abortable SSE streaming, chat persistence.
- **Security:** injection-safe filter construction, optional API-key auth, per-IP
  rate limiting, locked CORS.

> **Cost:** The default stack is **fully local — $0, offline, no rate limits**
> (local `bge-large` embeddings + a local oMLX/Ollama model; EDGAR + XBRL need no
> key). Cloud LLMs are optional: a free Cerebras key, or Gemini/Claude/OpenAI.
> Trade-off: local synthesis on a 27B is slower (~tens of seconds) than cloud. See
> [docs/HOSTING_AND_AI_OPTIONS.md](docs/HOSTING_AND_AI_OPTIONS.md).
