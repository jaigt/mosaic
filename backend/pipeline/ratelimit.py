"""
Thread-safe token-bucket rate limiter.

Used to govern outbound LLM calls during the table-summarization pass, which
runs across a ThreadPoolExecutor *inside* a worker thread (the caller invokes
``ingest_filing`` via ``asyncio.to_thread``). That rules out an asyncio-based
limiter — this one uses a plain ``threading.Lock`` plus ``time.monotonic`` for
lazy refill, so it is safe to share across the pool's worker threads.
"""
import threading
import time


class TokenBucket:
    """
    Classic token bucket.

    The bucket holds up to ``capacity`` tokens and refills continuously at
    ``rate_per_sec`` tokens/second. ``acquire`` removes one token, blocking
    (sleeping) until one is available. A freshly constructed bucket starts
    full, so the first ``capacity`` acquisitions return immediately (burst),
    after which throughput is capped at ``rate_per_sec``.
    """

    def __init__(self, rate_per_sec: float, capacity: int):
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._rate = float(rate_per_sec)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._lock = threading.Lock()
        self._last_refill = time.monotonic()

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

    def acquire(self, tokens: int = 1) -> None:
        """Block until ``tokens`` are available, then consume them."""
        if tokens <= 0:
            return
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                # Time until enough tokens have accrued.
                deficit = tokens - self._tokens
                wait = deficit / self._rate
            # Sleep OUTSIDE the lock so other threads can also make progress
            # toward their own (possibly already-satisfiable) requests.
            time.sleep(wait)
