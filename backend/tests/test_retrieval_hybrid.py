"""Tests for hybrid retrieval ranking math: lexical scoring + Reciprocal Rank
Fusion. All functions under test are pure (synthetic candidates, no LanceDB / no
embedding call).
"""
from backend.retrieval.hybrid import (
    tokenize,
    lexical_scores,
    reciprocal_rank_fusion,
    fuse_candidates,
)


# ── tokenize ─────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_splits_on_non_alnum():
    assert tokenize("Apple's Revenue, 2023!") == ["apple", "s", "revenue", "2023"]


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize("   ") == []


# ── lexical_scores (BM25-lite over the candidate set) ────────────────────────

def test_lexical_scores_ranks_overlap_highest():
    query = "gross margin trend"
    docs = [
        "the gross margin trend improved sharply",  # all 3 terms
        "gross margin held flat",                   # 2 terms
        "revenue grew in asia",                     # 0 terms
    ]
    scores = lexical_scores(query, docs)
    assert len(scores) == 3
    assert scores[0] > scores[1] > scores[2]
    assert scores[2] == 0.0


def test_lexical_scores_rewards_rare_terms_via_idf():
    # 'margin' appears in every doc (low idf); 'litigation' is rare (high idf).
    query = "litigation"
    docs = [
        "margin margin margin",
        "litigation risk disclosed",
        "margin pressure noted",
    ]
    scores = lexical_scores(query, docs)
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]


def test_lexical_scores_empty_query_is_all_zero():
    assert lexical_scores("", ["a b c", "d e f"]) == [0.0, 0.0]


def test_lexical_scores_empty_docs():
    assert lexical_scores("anything", []) == []


# ── reciprocal_rank_fusion (pure) ────────────────────────────────────────────

def test_rrf_combines_two_rankings():
    # ranking_a orders ids by one signal, ranking_b by another.
    ranking_a = ["x", "y", "z"]
    ranking_b = ["z", "y", "x"]
    fused = reciprocal_rank_fusion([ranking_a, ranking_b], k=60)
    # All three appear in both rankings exactly once; total positions are
    # symmetric, so fused scores should be (near-)equal across the board.
    vals = sorted(fused.values())
    assert max(vals) - min(vals) < 1e-3
    # x and z are perfectly symmetric (rank1+rank3 vs rank3+rank1).
    assert abs(fused["x"] - fused["z"]) < 1e-9


def test_rrf_higher_rank_scores_more():
    fused = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert fused["a"] > fused["b"] > fused["c"]


def test_rrf_handles_missing_ids_across_rankings():
    fused = reciprocal_rank_fusion([["a", "b"], ["c"]], k=60)
    assert set(fused) == {"a", "b", "c"}
    # 'a' appears once at rank1; 'c' appears once at rank1 → equal.
    assert abs(fused["a"] - fused["c"]) < 1e-9


# ── fuse_candidates (orchestrates vector order + lexical over candidates) ─────

def _cand(cid, text):
    return {"id": cid, "text": text}


def test_fuse_candidates_promotes_strong_lexical_match():
    # A chunk that the vector store ranked LAST but which is the only strong
    # lexical match should be pulled up above purely-semantic neighbours.
    query = "deferred revenue recognition policy"
    candidates = [
        _cand("v1", "general business overview and strategy"),
        _cand("v2", "competition and market risks"),
        _cand("v3", "our deferred revenue recognition policy is described here"),
    ]
    ranked = fuse_candidates(query, candidates, text_key="text", id_key="id", k=60)
    ranked_ids = [c["id"] for c in ranked]
    # v3 was vector-rank-3 but lexical-rank-1; fusion lifts it above v2.
    assert ranked_ids.index("v3") < ranked_ids.index("v2")
    assert set(ranked_ids) == {"v1", "v2", "v3"}
    # Fusion scores are attached for downstream relevance use.
    assert all("rrf_score" in c for c in ranked)


def test_fuse_candidates_preserves_all_candidates():
    query = "anything"
    candidates = [_cand(str(i), f"text {i}") for i in range(5)]
    ranked = fuse_candidates(query, candidates, text_key="text", id_key="id")
    assert len(ranked) == 5


def test_fuse_candidates_empty():
    assert fuse_candidates("q", [], text_key="text", id_key="id") == []
