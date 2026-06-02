"""Tests for the thread-safe token-bucket rate limiter."""
import threading
import time

import pytest

from backend.pipeline.ratelimit import TokenBucket


class TestTokenBucket:
    def test_burst_up_to_capacity_is_immediate(self):
        # A fresh bucket starts full; `capacity` acquires should not block.
        bucket = TokenBucket(rate_per_sec=10.0, capacity=5)
        start = time.monotonic()
        for _ in range(5):
            bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"burst should be immediate, took {elapsed:.3f}s"

    def test_acquires_beyond_capacity_are_throttled(self):
        # N rapid acquires beyond capacity must take ~ (N - capacity) / rate.
        rate = 20.0  # tokens/sec -> 0.05s per token
        capacity = 2
        n = 6
        bucket = TokenBucket(rate_per_sec=rate, capacity=capacity)
        start = time.monotonic()
        for _ in range(n):
            bucket.acquire()
        elapsed = time.monotonic() - start
        expected = (n - capacity) / rate  # 4 / 20 = 0.2s
        assert elapsed >= expected * 0.8, (
            f"expected >= {expected * 0.8:.3f}s, got {elapsed:.3f}s"
        )
        # Generous upper bound to avoid flakiness on a loaded CI box.
        assert elapsed <= expected + 0.5, (
            f"expected <= {expected + 0.5:.3f}s, got {elapsed:.3f}s"
        )

    def test_thread_safe_under_concurrency(self):
        # Many threads hammering the bucket must not exceed the rate budget.
        rate = 50.0
        capacity = 5
        n = 30
        bucket = TokenBucket(rate_per_sec=rate, capacity=capacity)
        errors = []

        def worker():
            try:
                bucket.acquire()
            except Exception as e:  # pragma: no cover - defensive
                errors.append(e)

        start = time.monotonic()
        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - start

        assert not errors, f"thread errors: {errors}"
        expected = (n - capacity) / rate  # 25 / 50 = 0.5s
        assert elapsed >= expected * 0.8, (
            f"concurrent acquires bypassed the rate limit: {elapsed:.3f}s "
            f"< {expected * 0.8:.3f}s"
        )

    def test_rejects_invalid_params(self):
        with pytest.raises(ValueError):
            TokenBucket(rate_per_sec=0, capacity=5)
        with pytest.raises(ValueError):
            TokenBucket(rate_per_sec=10, capacity=0)
