"""Re-ranking / diversification via Maximal Marginal Relevance (MMR).

After fusion we may still hold several near-duplicate chunks (e.g. boilerplate
risk-factor language repeated across filings). MMR greedily builds the final
top_k by trading off relevance against novelty relative to what's already
selected, so the synthesis context covers more distinct ground.

Similarity between chunks is approximated by token Jaccard — pure, cheap, and
embedding-free (we don't keep candidate vectors around at this stage). All
functions are PURE and unit-tested.
"""
from typing import Sequence

from backend.retrieval.hybrid import tokenize


def jaccard_similarity(a: str, b: str) -> float:
    """Token-set Jaccard similarity in [0, 1]. PURE."""
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def mmr_rerank(
    items: Sequence[dict],
    top_k: int,
    lambda_: float = 0.7,
    text_key: str = "text",
    relevance_key: str = "relevance",
) -> list[dict]:
    """Greedy Maximal Marginal Relevance reorder. PURE.

    Each item must carry a precomputed ``relevance`` score. At each step we pick
    the unselected item maximizing::

        lambda_ * relevance - (1 - lambda_) * max_sim_to_selected

    ``lambda_=1.0`` reduces to pure relevance ordering; lower values penalize
    redundancy more. Returns up to ``top_k`` items.
    """
    pool = list(items)
    if not pool:
        return []
    top_k = min(top_k, len(pool))

    selected: list[dict] = []
    remaining = list(pool)
    while remaining and len(selected) < top_k:
        best = None
        best_score = None
        for cand in remaining:
            rel = float(cand.get(relevance_key, 0.0))
            if selected:
                max_sim = max(
                    jaccard_similarity(cand.get(text_key, ""), s.get(text_key, ""))
                    for s in selected
                )
            else:
                max_sim = 0.0
            mmr = lambda_ * rel - (1.0 - lambda_) * max_sim
            if best_score is None or mmr > best_score:
                best_score = mmr
                best = cand
        selected.append(best)
        remaining.remove(best)
    return selected


def diversify(
    items: Sequence[dict],
    top_k: int,
    lambda_: float = 0.7,
    text_key: str = "text",
) -> list[dict]:
    """Diversify an already-ranked list. PURE.

    Convenience wrapper for the common case where ``items`` is already in
    descending relevance order but carries no explicit relevance score: we derive
    a descending relevance from rank position (best-first), then run MMR.
    """
    pool = list(items)
    if not pool:
        return []
    n = len(pool)
    annotated = []
    for rank, item in enumerate(pool):
        item = dict(item)
        # Linearly descending relevance in (0, 1]; preserves input order.
        item["_mmr_relevance"] = (n - rank) / n
        annotated.append(item)
    return mmr_rerank(
        annotated,
        top_k=top_k,
        lambda_=lambda_,
        text_key=text_key,
        relevance_key="_mmr_relevance",
    )
