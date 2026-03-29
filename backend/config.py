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

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
