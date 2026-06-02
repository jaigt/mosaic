from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    google_api_key: str
    anthropic_api_key: str = ""  # Optional — needed for claude-* models
    openai_api_key: str = ""     # Optional — needed for gpt-* / o* models
    sec_user_agent: str
    lancedb_path: str = "./data/lancedb"
    fast_model: str = "gemini-3.1-flash-lite-preview"
    synthesis_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    # Allowed browser origins for CORS. Comma-separated in .env; defaults to the
    # Vite dev server. Set to your deployed frontend origin in production.
    cors_allow_origins: list[str] = ["http://localhost:5173"]
    # Optional API key for cost-bearing endpoints (/ingest, /chat, /retrieve).
    # Empty = auth disabled (local dev). Set in .env to require X-API-Key.
    api_key: str = ""
    # Per-IP request budget per minute for cost-bearing endpoints. 0 = disabled.
    rate_limit_per_minute: int = 30

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
