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

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import settings

logger = logging.getLogger(__name__)


class EmbeddingRateLimit(Exception):
    """Raised when an embedding provider returns a rate-limit (429) error, so the
    retry layer waits long enough for a per-minute quota to refill."""


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "rate limit" in msg or "quota" in msg


# Embedding free tiers are throttled per-minute (e.g. Gemini's
# embed_content_free_tier_requests = 100/min). On a 429 we back off for up to a
# minute — long enough for the window to refill — rather than failing the whole
# ingest. Non-rate-limit errors are NOT retried (they won't fix themselves).
_embed_retry = retry(
    retry=retry_if_exception_type(EmbeddingRateLimit),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)

# Local (offline, on-CPU via fastembed/ONNX) embedding models. Routed by the
# "local-" prefix. These remove the API-key + free-tier-quota dependency for the
# entire ingest + retrieval path (only synthesis then needs a key). Each maps a
# short config name → (fastembed model id, dimension). Default to the LARGE bge
# model: on financial-filing retrieval the quality gap to a top proprietary
# embedder is smallest with a large model (measure with backend/eval).
_LOCAL_MODELS = {
    "local-bge-large": ("BAAI/bge-large-en-v1.5", 1024),
    "local-bge-base": ("BAAI/bge-base-en-v1.5", 768),
    "local-bge-small": ("BAAI/bge-small-en-v1.5", 384),
}

# Dimensions by model. Models must be listed here explicitly — silently
# defaulting an unknown model's dimension previously let a stale .env value
# (text-embedding-004 → 768) disagree with a 3072-dim LanceDB table.
_DIMS = {
    "gemini-embedding-001": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    # Legacy Google model (deprecated upstream); kept for old tables only.
    "text-embedding-004": 768,
    **{name: dim for name, (_id, dim) in _LOCAL_MODELS.items()},
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
    """Embed a batch of documents. Routes by model name: local-* (offline
    fastembed), text-embedding-3-* (OpenAI), else Google."""
    if not texts:
        return []
    model = settings.embedding_model
    if model.startswith("local-"):
        return _embed_local(list(texts), model, is_query=False)
    if model.startswith("text-embedding-3"):
        return _embed_openai(list(texts), model, task="document")
    return _embed_google(list(texts), model, task="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed a single query string (same routing as embed_texts)."""
    model = settings.embedding_model
    if model.startswith("local-"):
        return _embed_local([text], model, is_query=True)[0]
    if model.startswith("text-embedding-3"):
        return _embed_openai([text], model, task="query")[0]
    return _embed_google([text], model, task="RETRIEVAL_QUERY")[0]


# Cache the loaded fastembed model process-wide — construction downloads (first
# run) and memory-maps the ONNX weights, which is far too expensive per call.
_local_model_cache: dict = {}


def _get_local_model(model: str):
    """Resolve a ``local-*`` config name to a cached fastembed TextEmbedding."""
    if model not in _LOCAL_MODELS:
        raise ValueError(
            f"Unknown local embedding model '{model}'. Known: {sorted(_LOCAL_MODELS)}"
        )
    if model not in _local_model_cache:
        from fastembed import TextEmbedding  # lazy: heavy import + model load
        fastembed_id, _dim = _LOCAL_MODELS[model]
        logger.info(f"Loading local embedding model '{fastembed_id}' (first run downloads it)")
        _local_model_cache[model] = TextEmbedding(model_name=fastembed_id)
    return _local_model_cache[model]


def _embed_local(texts: list[str], model: str, is_query: bool) -> list[list[float]]:
    """Embed locally via fastembed (ONNX on CPU). No network, no API key.

    Uses ``query_embed`` for queries so retrieval-tuned models (e.g. bge) apply
    their query instruction prefix; ``embed`` for documents. fastembed yields
    numpy arrays — convert to plain float lists for LanceDB.
    """
    embedder = _get_local_model(model)
    gen = embedder.query_embed(texts) if is_query else embedder.embed(texts)
    return [vec.tolist() for vec in gen]


@_embed_retry
def _embed_google_batch(client, model: str, batch: list[str], task: str) -> list[list[float]]:
    """Embed one batch; translate a 429 into EmbeddingRateLimit so it's retried."""
    try:
        response = client.models.embed_content(
            model=model, contents=batch, config={"task_type": task},
        )
    except Exception as e:
        if _is_rate_limit(e):
            logger.warning(f"Embedding rate-limited; backing off: {str(e)[:120]}")
            raise EmbeddingRateLimit(str(e)) from e
        raise
    return [e.values for e in response.embeddings]


def _embed_google(texts: list[str], model: str, task: str) -> list[list[float]]:
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        results.extend(_embed_google_batch(client, model, batch, task))
        if i + batch_size < len(texts):
            time.sleep(_BATCH_DELAY)
    logger.debug(f"Google embedded {len(texts)} texts")
    return results


@_embed_retry
def _embed_openai_batch(client, model: str, batch: list[str]) -> list[list[float]]:
    """Embed one batch; translate a 429 into EmbeddingRateLimit so it's retried."""
    try:
        response = client.embeddings.create(model=model, input=batch)
    except Exception as e:
        if _is_rate_limit(e):
            logger.warning(f"Embedding rate-limited; backing off: {str(e)[:120]}")
            raise EmbeddingRateLimit(str(e)) from e
        raise
    return [e.embedding for e in response.data]


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
        results.extend(_embed_openai_batch(client, model, batch))
        if i + batch_size < len(texts):
            time.sleep(_BATCH_DELAY)
    logger.debug(f"OpenAI embedded {len(texts)} texts")
    return results
