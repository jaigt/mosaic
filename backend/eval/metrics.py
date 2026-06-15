"""Pure retrieval-evaluation metrics.

A retrieval change (new hybrid weights, MMR lambda, chunk overlap, embedding
model) should be judged on numbers, not vibes. These functions score a ranked
list of retrieved chunks against a labelled expectation. They are PURE — no
network, no LLM — so they unit-test without an API key. The live runner that
actually calls ``retrieve`` lives in ``harness.py``.

A retrieved item is considered relevant to a case when its chunk's ticker
matches and (if the case specifies them) the document_type, year, and a
case-insensitive substring of the section all match.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalCase:
    """One labelled retrieval expectation."""

    query: str
    ticker: str
    section_contains: Optional[str] = None   # substring of sec_item_section
    doc_type: Optional[str] = None           # "10-K" | "10-Q" | ...
    year: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        return cls(
            query=d["query"],
            ticker=d["ticker"],
            section_contains=d.get("section_contains"),
            doc_type=d.get("doc_type"),
            year=d.get("year"),
        )


def case_matches(case: EvalCase, chunk) -> bool:
    """Whether a retrieved ``chunk`` satisfies the case's expectation. PURE."""
    if (getattr(chunk, "ticker", "") or "").upper() != case.ticker.upper():
        return False
    if case.doc_type and getattr(chunk, "document_type", None) != case.doc_type:
        return False
    if case.year and getattr(chunk, "filing_year", None) != case.year:
        return False
    if case.section_contains:
        section = (getattr(chunk, "sec_item_section", "") or "").lower()
        if case.section_contains.lower() not in section:
            return False
    return True


def rank_of_first_match(case: EvalCase, retrieved: list) -> Optional[int]:
    """1-based rank of the first relevant retrieved item, or None. PURE.

    ``retrieved`` is a ranked list of objects exposing ``.chunk`` (as
    RetrievedChunk does).
    """
    for i, item in enumerate(retrieved, start=1):
        chunk = getattr(item, "chunk", item)
        if case_matches(case, chunk):
            return i
    return None


def hit_at_k(case: EvalCase, retrieved: list, k: int) -> bool:
    """Did a relevant item appear in the top-k? PURE."""
    rank = rank_of_first_match(case, retrieved)
    return rank is not None and rank <= k


def reciprocal_rank(case: EvalCase, retrieved: list) -> float:
    """1/rank of the first relevant item (0.0 if none). PURE."""
    rank = rank_of_first_match(case, retrieved)
    return 1.0 / rank if rank else 0.0


@dataclass
class CaseResult:
    case: EvalCase
    rank: Optional[int]
    reciprocal_rank: float


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)
    ks: tuple[int, ...] = (1, 3, 5)

    @property
    def n(self) -> int:
        return len(self.results)

    def hit_rate_at(self, k: int) -> float:
        if not self.results:
            return 0.0
        hits = sum(1 for r in self.results if r.rank is not None and r.rank <= k)
        return hits / len(self.results)

    @property
    def mrr(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.reciprocal_rank for r in self.results) / len(self.results)

    def summary(self) -> dict:
        out = {"n": self.n, "mrr": round(self.mrr, 4)}
        for k in self.ks:
            out[f"hit@{k}"] = round(self.hit_rate_at(k), 4)
        return out


def score_case(case: EvalCase, retrieved: list) -> CaseResult:
    """Score a single case against its retrieved list. PURE."""
    rank = rank_of_first_match(case, retrieved)
    return CaseResult(case=case, rank=rank, reciprocal_rank=(1.0 / rank if rank else 0.0))


def build_report(cases: list[EvalCase], retrieved_per_case: list[list], ks=(1, 3, 5)) -> EvalReport:
    """Assemble an EvalReport from cases and their (already retrieved) results. PURE."""
    if len(cases) != len(retrieved_per_case):
        raise ValueError("cases and retrieved_per_case must be the same length")
    results = [score_case(c, r) for c, r in zip(cases, retrieved_per_case)]
    return EvalReport(results=results, ks=ks)
