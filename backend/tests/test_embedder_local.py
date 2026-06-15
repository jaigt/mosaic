"""Tests for the local (fastembed) embedding route.

fastembed is monkeypatched so no model download / ONNX run happens — we verify
routing, the query-vs-document API selection, dimension registration, and
caching.
"""
import numpy as np
import pytest

import backend.pipeline.embedder as emb


def test_local_dims_registered():
    assert emb._get_dim("local-bge-large") == 1024
    assert emb._get_dim("local-bge-base") == 768
    assert emb._get_dim("local-bge-small") == 384


def test_unknown_local_model_raises():
    with pytest.raises(ValueError, match="Unknown local embedding model"):
        emb._get_local_model("local-nope")


class _FakeFastEmbed:
    """Records which method was called; returns numpy vectors."""

    def __init__(self):
        self.embed_calls = []
        self.query_calls = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        for _ in texts:
            yield np.array([0.1, 0.2, 0.3], dtype=np.float32)

    def query_embed(self, texts):
        self.query_calls.append(list(texts))
        for _ in texts:
            yield np.array([0.9, 0.8, 0.7], dtype=np.float32)


@pytest.fixture
def fake_local(monkeypatch):
    fake = _FakeFastEmbed()
    emb._local_model_cache.clear()
    monkeypatch.setattr(emb, "_get_local_model", lambda model: fake)
    return fake


def test_embed_texts_routes_to_local_document_path(monkeypatch, fake_local):
    monkeypatch.setattr(emb.settings, "embedding_model", "local-bge-large")
    out = emb.embed_texts(["doc one", "doc two"])
    assert out == [[pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]] * 2
    assert fake_local.embed_calls == [["doc one", "doc two"]]   # used embed(), not query_embed()
    assert fake_local.query_calls == []


def test_embed_query_routes_to_local_query_path(monkeypatch, fake_local):
    monkeypatch.setattr(emb.settings, "embedding_model", "local-bge-large")
    out = emb.embed_query("what was revenue?")
    assert out == [pytest.approx(0.9), pytest.approx(0.8), pytest.approx(0.7)]
    assert fake_local.query_calls == [["what was revenue?"]]    # query instruction path
    assert fake_local.embed_calls == []


def test_local_model_is_cached(monkeypatch):
    emb._local_model_cache.clear()
    loads = {"n": 0}

    class Dummy:
        def embed(self, texts):
            return iter([])

    def fake_ctor(model_name):
        loads["n"] += 1
        return Dummy()

    import sys, types
    fake_mod = types.ModuleType("fastembed")
    fake_mod.TextEmbedding = fake_ctor
    monkeypatch.setitem(sys.modules, "fastembed", fake_mod)

    emb._get_local_model("local-bge-base")
    emb._get_local_model("local-bge-base")
    assert loads["n"] == 1   # constructed once, then cached
