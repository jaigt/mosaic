"""Tests for explicit embedding-dimension registration.

An unknown embedding model must fail loudly instead of silently defaulting to
768 — a silent default previously let a stale .env value disagree with a
3072-dim LanceDB table.
"""
import pytest

from backend.pipeline.embedder import _DIMS, _get_dim


def test_known_models_have_dims():
    assert _get_dim("gemini-embedding-001") == 3072
    assert _get_dim("text-embedding-3-small") == 1536
    assert _get_dim("text-embedding-3-large") == 3072


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="Unknown embedding model"):
        _get_dim("some-future-model")


def test_dims_registry_is_nonempty():
    assert _DIMS
