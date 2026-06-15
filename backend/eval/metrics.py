"""Pure retrieval-evaluation metrics.

A retrieval change (new hybrid weights, MMR lambda, chunk overlap, embedding
model) should be judged on numbers, not vibes. These functions score a ranked
list of retrieved chunks against a labelled expectation. They are PURE — no
network, no LLM — so they unit-test without an API key. The live runner that
actually calls ``retrieve`` lives in ``harness.py``.

A retrieved item is considered relevant to a case when its chunk's ticker
matches and (if the case specifies them) the document_type, year, and the
section all match. Section matching is satisfied when the chunk's section
contains ANY of the case's accepted substrings (case-insensitive) — see
``section_any_of`` / ``section_contains``.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalCase:
    """One labelled retrieval expectation.

    Section matching accepts a *list* of substrings (``section_any_of``): a
    chunk's section qualifies if it contains any of them (case-insensitive).
    Real filings often answer the same question from different sections (a
    revenue figure lives in the Income Statement *and* is discussed in MD&A),
    so a single rigid label produces false misses. ``section_contains`` remains
    as a single-substring shorthand and is folded into ``section_any_of``.
    """

    query: str
    ticker: str
    section_contains: Optional[str] = None      # single-substring shorthand
    doc_type: Optional[str] = None              # "10-K" | "10-Q" | ...
    year: Optional[int] = None
    section_any_of: Optional[list[str]] = None  # any-of substrings of section

    def accepted_sections(self) -> list[str]:
        """All section substrings that satisfy this case (deduped, non-empty)."""
        out: list[str] = []
        if self.section_contains:
            out.append(self.section_contains)
        if self.section_any_of:
            out.extend(self.section_any_of)
        return [s for s in out if s]

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        return cls(
            query=d["query"],
            ticker=d["ticker"],
            section_contains=d.get("section_contains"),
            doc_type=d.get("doc_type"),
            year=d.get("year"),
            section_any_of=d.get("section_any_of"),
        )


def case_matches(case: EvalCase, chunk) -> bool:
    """Whether a retrieved ``chunk`` satisfies the case's expectation. PURE."""
    if (getattr(chunk, "ticker", "") or "").upper() != case.ticker.upper():
        return False
    if case.doc_type and getattr(chunk, "document_type", None) != case.doc_type:
        return False
    if case.year and getattr(chunk, "filing_year", None) != case.year:
        return False
    accepted = case.accepted_sections()
    if accepted:
        section = (getattr(chunk, "sec_item_section", "") or "").lower()
        if not any(s.lower() in section for s in accepted):
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
