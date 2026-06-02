"""
Lightweight auth + per-IP rate limiting for cost-bearing endpoints
(/ingest, /chat, /retrieve) which trigger paid LLM calls and EDGAR fetches.

Both are no-ops by default so local development is unaffected:
  * API key: enforced only when settings.api_key is non-empty.
  * Rate limit: disabled when settings.rate_limit_per_minute <= 0.

In-memory and per-process (fine for a single-worker POC; use Redis for a
multi-worker deployment).
"""
import threading
import time
from typing import Optional

from fastapi import Header, HTTPException, Request

from backend.config import settings


class TokenBucket:
    """Thread-safe token bucket. ``allow()`` is non-blocking."""

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_per_sec = refill_per_sec
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(
                self.capacity, self.tokens + (now - self._updated) * self.refill_per_sec
            )
            self._updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


class RateLimiter:
    """Per-key (per-IP) token-bucket rate limiter."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(self.per_minute, self.per_minute / 60.0)
                self._buckets[key] = bucket
        return bucket.allow()


_limiter = RateLimiter(settings.rate_limit_per_minute)


def verify_api_key(provided: Optional[str]) -> None:
    """Raise 401 if an API key is configured and the provided one doesn't match."""
    if settings.api_key and provided != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    verify_api_key(x_api_key)


def enforce_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not _limiter.allow(client):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
