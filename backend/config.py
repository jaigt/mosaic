from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    google_api_key: str
    anthropic_api_key: str = ""  # Optional — needed for claude-* models
    openai_api_key: str = ""     # Optional — needed for gpt-* / o* models
    sec_user_agent: str
    lancedb_path: str = "./data/lancedb"
    fast_model: str = "gemini-2.0-flash"
    synthesis_model: str = "gemini-2.5-pro-preview-03-25"
    embedding_model: str = "text-embedding-004"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
