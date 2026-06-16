from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    google_api_key: str = ""     # Optional — needed for gemini-* models
    anthropic_api_key: str = ""  # Optional — needed for claude-* models
    openai_api_key: str = ""     # Optional — needed for gpt-* / o* models
    # OpenAI-compatible free/cheap providers, reached by prefixing the model with
    # "<provider>/", e.g. SYNTHESIS_MODEL="cerebras/llama-3.3-70b". All three have
    # a no-credit-card free tier far more generous than Gemini's daily cap:
    #   cerebras → ~1M tokens/DAY      groq → ~1k req/day, fastest streaming
    #   mistral  → ~1B tokens/MONTH
    # Ollama ("ollama/<model>") needs no key at all — fully local, no limits.
    cerebras_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    # oMLX / mlx_lm OpenAI-compatible server. oMLX defaults to :8000 — which
    # collides with this backend — so point it at a different port (e.g. 8081)
    # in the oMLX app and set MLX_BASE_URL to match. Use via "mlx/<model>".
    mlx_base_url: str = "http://localhost:8081/v1"
    # oMLX can require an API key on /v1 (Security tab). Set MLX_API_KEY to match;
    # leave empty if you disable key verification. Sent as the Bearer token.
    mlx_api_key: str = ""
    sec_user_agent: str
    lancedb_path: str = "./data/lancedb"
    # SQLite store for the structured financial fact base (local, gitignored).
    facts_db_path: str = "./data/facts.db"
    # SQLite store for the watchlist + view snapshots (local, gitignored).
    watchlist_db_path: str = "./data/watchlist.db"
    # Stable GA models (verified live 2026-06-15). NOT *-preview: this project
    # was burned before by pinning retired preview names (see docs round 3).
    fast_model: str = "gemini-2.5-flash-lite"
    synthesis_model: str = "gemini-2.5-flash"
    # Default to LOCAL embeddings (fastembed/ONNX, "local-*" prefix): ingest +
    # retrieval then need no embedding key and hit no free-tier quota wall (only
    # synthesis/fast use a key). Swap to gemini-embedding-001 / text-embedding-3-*
    # for a hosted embedder — changing the dimension requires a re-ingest.
    embedding_model: str = "local-bge-large"
    # Allowed browser origins for CORS. Comma-separated in .env; defaults to the
    # Vite dev server. Set to your deployed frontend origin in production.
    cors_allow_origins: list[str] = ["http://localhost:5173"]
    # Optional API key for cost-bearing endpoints (/ingest, /chat, /retrieve).
    # Empty = auth disabled (local dev). Set in .env to require X-API-Key.
    api_key: str = ""
    # Per-IP request budget per minute for cost-bearing endpoints. 0 = disabled.
    rate_limit_per_minute: int = 30

    # ── Ingestion table-summarization throughput ────────────────────────────
    # The table-summary pass is the dominant ingestion cost: each table is a
    # fast-LLM call, throttled to the provider's requests-per-minute budget.
    # Defaults are tuned for the Gemini AI Studio FREE tier (~15 RPM). Batching
    # several tables per call is what actually beats the RPM ceiling — raise the
    # batch size and RPM together when running on a paid key.
    table_summary_rpm: int = 15          # provider requests/min for the fast model
    # Max in-flight summary calls. Kept low (2) because free tiers throttle hard
    # on bursts — e.g. Cerebras free is ~1 req/sec, so a 5-wide burst instantly
    # trips a 429. Raise on a paid key or a local model (no rate limit).
    table_summary_concurrency: int = 2
    table_summary_batch_size: int = 6    # tables summarized per LLM call (>=1)

    # ── Agentic chat behaviour ──────────────────────────────────────────────
    # Corpus autonomy: when a query names a ticker the corpus lacks, fetch that
    # filing from EDGAR mid-answer, then re-search. Self-verification: a critic
    # pass checks the answer's claims against the retrieved sources. Both add
    # LLM calls per query — disable to minimize cost/latency on the free tier.
    enable_auto_ingest: bool = True
    enable_self_verification: bool = True
    # Extract a normalized financial fact base (XBRL → SQLite) during ingest.
    # Deterministic, no LLM; powers get_financials + the valuation engine.
    enable_fact_extraction: bool = True

    # Multi-tool ReAct agent: when on, chat runs a model-driven tool loop
    # (search / ingest / list_corpus over multiple steps) to gather evidence
    # before synthesizing — generalizing the fixed auto-ingest pipeline above.
    # When off, the fixed round-5 pipeline is used. ``agent_model`` is the model
    # that drives the loop's reasoning; empty = fall back to ``synthesis_model``.
    enable_react_agent: bool = True
    agent_model: str = ""
    agent_max_steps: int = 5

    # Smart-money (superinvestor 13F) index auto-refresh. On startup, if the
    # cached index is missing or older than ``smart_money_stale_days``, the app
    # rebuilds it in the background (13Fs refile quarterly, ~45 days after
    # quarter-end). Keeps "which funds hold X" current without manual refreshes.
    smart_money_auto_refresh: bool = True
    smart_money_stale_days: int = 30
    # Use native provider function-calling for the ReAct loop (vs parsing JSON
    # actions from text). More reliable, but provider-specific (Gemini only so
    # far). Default OFF until broadly live-verified; text-ReAct is the proven
    # default and is used automatically for providers without native support.
    agent_native_tools: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
