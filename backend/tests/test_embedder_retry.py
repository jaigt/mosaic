"""Tests for embedding rate-limit classification and retry/backoff.

The wait is monkeypatched to zero so the retry logic is exercised instantly.
"""
import pytest

import backend.pipeline.embedder as emb


def test_is_rate_limit_classification():
    assert emb._is_rate_limit(Exception("429 RESOURCE_EXHAUSTED"))
    assert emb._is_rate_limit(Exception("Quota exceeded for metric ..."))
    assert emb._is_rate_limit(Exception("rate limit reached"))
    assert not emb._is_rate_limit(Exception("invalid api key"))
    assert not emb._is_rate_limit(Exception("model not found 404"))


def _no_wait(monkeypatch):
    # Strip the backoff sleep so retries run instantly in tests.
    monkeypatch.setattr(emb._embed_google_batch.retry, "wait", lambda *a, **k: 0)
    monkeypatch.setattr(emb._embed_openai_batch.retry, "wait", lambda *a, **k: 0)


class _Resp:
    def __init__(self, n):
        self.embeddings = [type("E", (), {"values": [0.1, 0.2]})() for _ in range(n)]


def test_google_batch_retries_then_succeeds(monkeypatch):
    _no_wait(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        class models:
            @staticmethod
            def embed_content(model, contents, config):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
                return _Resp(len(contents))

    out = emb._embed_google_batch(FakeClient(), "gemini-embedding-001", ["a", "b"], "RETRIEVAL_DOCUMENT")
    assert calls["n"] == 3          # failed twice, succeeded on the third
    assert len(out) == 2


def test_google_batch_does_not_retry_non_rate_limit(monkeypatch):
    _no_wait(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        class models:
            @staticmethod
            def embed_content(model, contents, config):
                calls["n"] += 1
                raise RuntimeError("invalid api key")

    with pytest.raises(RuntimeError, match="invalid api key"):
        emb._embed_google_batch(FakeClient(), "m", ["a"], "RETRIEVAL_DOCUMENT")
    assert calls["n"] == 1          # not retried


def test_google_batch_gives_up_after_persistent_rate_limit(monkeypatch):
    _no_wait(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        class models:
            @staticmethod
            def embed_content(model, contents, config):
                calls["n"] += 1
                raise RuntimeError("429 quota exceeded")

    with pytest.raises(emb.EmbeddingRateLimit):
        emb._embed_google_batch(FakeClient(), "m", ["a"], "RETRIEVAL_DOCUMENT")
    assert calls["n"] == 6          # stop_after_attempt(6)
