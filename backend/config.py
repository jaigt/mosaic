from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    google_api_key: str
    anthropic_api_key: str = ""  # Optional — needed for claude-* models
    openai_api_key: str = ""     # Optional — needed for gpt-* / o* models
    sec_user_agent: str
    lancedb_path: str = "./data/lancedb"
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
    table_summary_concurrency: int = 5   # max in-flight summary calls
    table_summary_batch_size: int = 6    # tables summarized per LLM call (>=1)

    # ── Agentic chat behaviour ──────────────────────────────────────────────
    # Corpus autonomy: when a query names a ticker the corpus lacks, fetch that
    # filing from EDGAR mid-answer, then re-search. Self-verification: a critic
    # pass checks the answer's claims against the retrieved sources. Both add
    # LLM calls per query — disable to minimize cost/latency on the free tier.
    enable_auto_ingest: bool = True
    enable_self_verification: bool = True

    # Multi-tool ReAct agent: when on, chat runs a model-driven tool loop
    # (search / ingest / list_corpus over multiple steps) to gather evidence
    # before synthesizing — generalizing the fixed auto-ingest pipeline above.
    # When off, the fixed round-5 pipeline is used. ``agent_model`` is the model
    # that drives the loop's reasoning; empty = fall back to ``synthesis_model``.
    enable_react_agent: bool = True
    agent_model: str = ""
    agent_max_steps: int = 5

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
