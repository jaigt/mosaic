"""Hybrid retrieval via Reciprocal Rank Fusion (no new index).

We over-fetch top-N candidates from the vector store, compute a cheap lexical
(BM25-lite) score over just that candidate set in pure Python, then fuse the
vector rank and the lexical rank with Reciprocal Rank Fusion (RRF). This adds
keyword sensitivity (tickers, section names, rare financial terms) on top of
semantic recall without standing up a separate full-text index.

All functions here are PURE and unit-tested with synthetic candidates.
"""
import math
import re
from collections import Counter
from typing import Any, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase and split on non-alphanumeric runs. PURE."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def lexical_scores(query: str, docs: Sequence[str]) -> list[float]:
    """BM25-lite relevance of ``query`` against each doc, scored over the
    candidate set only (idf is computed from ``docs``). PURE.

    Returns one score per doc, in the same order. Higher is more relevant;
    non-matching docs score 0.0.
    """
    if not docs:
        return []
    query_terms = set(tokenize(query))
    if not query_terms:
        return [0.0] * len(docs)

    tokenized = [tokenize(d) for d in docs]
    n = len(docs)
    avgdl = sum(len(t) for t in tokenized) / n if n else 0.0

    # Document frequency for each query term within the candidate set.
    df: Counter = Counter()
    for terms in tokenized:
        present = set(terms)
        for q in query_terms:
            if q in present:
                df[q] += 1

    # BM25 parameters (standard defaults).
    k1, b = 1.5, 0.75
    scores: list[float] = []
    for terms in tokenized:
        if not terms:
            scores.append(0.0)
            continue
        tf = Counter(terms)
        dl = len(terms)
        score = 0.0
        for q in query_terms:
            f = tf.get(q, 0)
            if f == 0:
                continue
            # Smoothed idf; +1 inside log keeps it strictly positive so a term
            # present in every candidate still contributes (just less).
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            denom = f + k1 * (1 - b + b * (dl / avgdl if avgdl else 1.0))
            score += idf * (f * (k1 + 1)) / denom
        scores.append(score)
    return scores


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Any]], k: int = 60
) -> dict:
    """Fuse multiple ranked id-lists into a combined score per id. PURE.

    For each ranking, an id at 0-based position ``r`` contributes ``1/(k+r+1)``.
    Larger ``k`` flattens the contribution curve. Returns {id: fused_score}.
    """
    fused: dict = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return fused


def fuse_candidates(
    query: str,
    candidates: Sequence[dict],
    text_key: str = "text",
    id_key: str = "id",
    k: int = 60,
) -> list[dict]:
    """Re-order ``candidates`` by fusing their incoming (vector) order with a
    lexical ranking over the candidate set. PURE.

    ``candidates`` must already be in vector-similarity order (best first). Each
    candidate is annotated in-place with ``rrf_score`` and returned sorted by it
    (descending). Ties keep the original vector order (stable sort).
    """
    if not candidates:
        return []

    ids = [c[id_key] for c in candidates]
    vector_order = list(ids)  # candidates arrive best-first from the vector store

    lex = lexical_scores(query, [c.get(text_key, "") for c in candidates])
    # Lexical ranking: ids sorted by lexical score desc; stable on vector order.
    lexical_order = [
        ids[i]
        for i in sorted(range(len(ids)), key=lambda i: (-lex[i], i))
    ]

    fused = reciprocal_rank_fusion([vector_order, lexical_order], k=k)

    annotated = list(candidates)
    for c in annotated:
        c["rrf_score"] = fused.get(c[id_key], 0.0)

    order_index = {cid: i for i, cid in enumerate(ids)}
    return sorted(
        annotated,
        key=lambda c: (-c["rrf_score"], order_index[c[id_key]]),
    )
