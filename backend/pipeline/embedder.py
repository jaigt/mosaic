"""
Provider-agnostic embedding layer.
  gemini-embedding-*  → Google (3072-dim, supports task_type)
  text-embedding-3-*  → OpenAI (1536-dim for -small, 3072 for -large)

Note: Anthropic has no embedding API.
POC Decision: Defaults to gemini-embedding-001 via Google AI Studio free tier.

EMBEDDING_DIM is baked into the LanceDB schema at table creation, so changing
the embedding model requires a new table + re-ingest (see store.get_table,
which validates the dimension of an existing table against this module).
"""
import logging
import time
from typing import Sequence

from backend.config import settings

logger = logging.getLogger(__name__)

# Dimensions by model. Models must be listed here explicitly — silently
# defaulting an unknown model's dimension previously let a stale .env value
# (text-embedding-004 → 768) disagree with a 3072-dim LanceDB table.
_DIMS = {
    "gemini-embedding-001": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    # Legacy Google model (deprecated upstream); kept for old tables only.
    "text-embedding-004": 768,
}

def _get_dim(model: str) -> int:
    try:
        return _DIMS[model]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model '{model}': its vector dimension is not "
            f"registered. Add it to _DIMS in backend/pipeline/embedder.py. "
            f"Known models: {sorted(_DIMS)}"
        ) from None

EMBEDDING_DIM = _get_dim(settings.embedding_model)

_BATCH_DELAY = 0.05


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of documents. Routes to Google or OpenAI based on model name."""
    if not texts:
        return []
    model = settings.embedding_model
    if model.startswith("text-embedding-3"):
        return _embed_openai(list(texts), model, task="document")
    return _embed_google(list(texts), model, task="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    model = settings.embedding_model
    if model.startswith("text-embedding-3"):
        return _embed_openai([text], model, task="query")[0]
    return _embed_google([text], model, task="RETRIEVAL_QUERY")[0]


def _embed_google(texts: list[str], model: str, task: str) -> list[list[float]]:
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.models.embed_content(
            model=model,
            contents=batch,
            config={"task_type": task},
        )
        results.extend([e.values for e in response.embeddings])
        if i + batch_size < len(texts):
            time.sleep(_BATCH_DELAY)
    logger.debug(f"Google embedded {len(texts)} texts")
    return results


def _embed_openai(texts: list[str], model: str, task: str) -> list[list[float]]:
    from openai import OpenAI
    key = settings.openai_api_key
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY required for embedding model '{model}'")
    client = OpenAI(api_key=key)
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        results.extend([e.embedding for e in response.data])
        if i + batch_size < len(texts):
            time.sleep(_BATCH_DELAY)
    logger.debug(f"OpenAI embedded {len(texts)} texts")
    return results
