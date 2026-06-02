"""Tests for API auth + rate limiting (backend.api.security)."""
import time

import pytest
from fastapi import HTTPException

from backend.api.security import RateLimiter, TokenBucket, verify_api_key
from backend.config import settings


class TestTokenBucket:
    def test_allows_up_to_capacity_then_denies(self):
        bucket = TokenBucket(capacity=3, refill_per_sec=0)  # no refill
        assert bucket.allow() is True
        assert bucket.allow() is True
        assert bucket.allow() is True
        assert bucket.allow() is False

    def test_refills_over_time(self):
        bucket = TokenBucket(capacity=1, refill_per_sec=20)  # ~1 token / 50ms
        assert bucket.allow() is True
        assert bucket.allow() is False
        time.sleep(0.12)
        assert bucket.allow() is True


class TestRateLimiter:
    def test_disabled_when_zero(self):
        limiter = RateLimiter(per_minute=0)
        for _ in range(100):
            assert limiter.allow("1.2.3.4") is True

    def test_limits_per_key(self):
        limiter = RateLimiter(per_minute=2)
        assert limiter.allow("a") is True
        assert limiter.allow("a") is True
        assert limiter.allow("a") is False

    def test_keys_are_independent(self):
        limiter = RateLimiter(per_minute=1)
        assert limiter.allow("a") is True
        assert limiter.allow("b") is True  # different key, own bucket
        assert limiter.allow("a") is False


class TestVerifyApiKey:
    def test_no_key_configured_allows_all(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "")
        verify_api_key(None)        # no raise
        verify_api_key("anything")  # no raise

    def test_configured_key_requires_match(self, monkeypatch):
        monkeypatch.setattr(settings, "api_key", "secret")
        verify_api_key("secret")  # no raise
        with pytest.raises(HTTPException) as exc:
            verify_api_key("wrong")
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException):
            verify_api_key(None)
