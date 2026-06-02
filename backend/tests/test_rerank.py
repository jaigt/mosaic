"""Tests for MMR-style diversification / near-duplicate suppression. Pure
ranking math over synthetic candidates — no embeddings, no network.
"""
from backend.retrieval.rerank import (
    jaccard_similarity,
    mmr_rerank,
    diversify,
)


# ── jaccard_similarity ───────────────────────────────────────────────────────

def test_jaccard_identical_is_one():
    assert jaccard_similarity("gross margin trend", "gross margin trend") == 1.0


def test_jaccard_disjoint_is_zero():
    assert jaccard_similarity("apple revenue", "microsoft cloud") == 0.0


def test_jaccard_partial_overlap():
    # tokens {a,b,c} vs {b,c,d} → intersection 2, union 4 → 0.5
    assert jaccard_similarity("a b c", "b c d") == 0.5


def test_jaccard_empty_is_zero():
    assert jaccard_similarity("", "anything") == 0.0
    assert jaccard_similarity("", "") == 0.0


# ── mmr_rerank ───────────────────────────────────────────────────────────────

def test_mmr_picks_highest_relevance_first():
    items = [
        {"id": "a", "text": "alpha", "relevance": 0.2},
        {"id": "b", "text": "beta", "relevance": 0.9},
        {"id": "c", "text": "gamma", "relevance": 0.5},
    ]
    out = mmr_rerank(items, top_k=3, lambda_=0.7, text_key="text", relevance_key="relevance")
    assert out[0]["id"] == "b"  # highest relevance always selected first


def test_mmr_demotes_near_duplicate_of_already_selected():
    items = [
        {"id": "a", "text": "gross margin expanded materially", "relevance": 0.90},
        {"id": "dup", "text": "gross margin expanded materially", "relevance": 0.89},
        {"id": "diverse", "text": "litigation reserves increased", "relevance": 0.80},
    ]
    out = mmr_rerank(items, top_k=2, lambda_=0.5, text_key="text", relevance_key="relevance")
    ids = [i["id"] for i in out]
    assert ids[0] == "a"
    # Even though 'dup' has higher raw relevance than 'diverse', it is a near
    # duplicate of 'a', so the diverse chunk is preferred second.
    assert ids[1] == "diverse"


def test_mmr_respects_top_k():
    items = [{"id": str(i), "text": f"unique text {i}", "relevance": 1.0 - i * 0.1} for i in range(5)]
    out = mmr_rerank(items, top_k=3, text_key="text", relevance_key="relevance")
    assert len(out) == 3


def test_mmr_top_k_larger_than_input_returns_all():
    items = [{"id": "a", "text": "x", "relevance": 0.5}]
    out = mmr_rerank(items, top_k=10, text_key="text", relevance_key="relevance")
    assert len(out) == 1


def test_mmr_empty():
    assert mmr_rerank([], top_k=5, text_key="text", relevance_key="relevance") == []


def test_mmr_lambda_one_is_pure_relevance_order():
    items = [
        {"id": "a", "text": "same same same", "relevance": 0.5},
        {"id": "b", "text": "same same same", "relevance": 0.9},
        {"id": "c", "text": "same same same", "relevance": 0.7},
    ]
    out = mmr_rerank(items, top_k=3, lambda_=1.0, text_key="text", relevance_key="relevance")
    assert [i["id"] for i in out] == ["b", "c", "a"]


# ── diversify (derives relevance from rank order when no score given) ─────────

def test_diversify_assigns_descending_relevance_from_input_order():
    # No relevance key — order itself is the relevance signal (already fused).
    items = [
        {"id": "a", "text": "gross margin expanded materially"},
        {"id": "dup", "text": "gross margin expanded materially"},
        {"id": "c", "text": "litigation reserves increased"},
    ]
    out = diversify(items, top_k=2, lambda_=0.5, text_key="text")
    ids = [i["id"] for i in out]
    assert ids[0] == "a"
    assert ids[1] == "c"  # duplicate suppressed


def test_diversify_empty():
    assert diversify([], top_k=3, text_key="text") == []
