"""Offline retrieval-eval runner.

Loads a labelled eval set, runs the real retriever for each query, scores the
ranked results with the pure metrics in ``metrics.py``, and prints aggregate
hit-rate / MRR numbers. Use it to make retrieval-tuning decisions (hybrid
weights, MMR lambda, chunk overlap, embedding model) data-driven.

Requires a populated corpus and a valid embedding key (it calls the live
retriever). The corpus must already contain the filings the eval set references
— ingest them first. Run:

    ./.venv/bin/python -m backend.eval.harness
    ./.venv/bin/python -m backend.eval.harness --top-k 5 --set backend/eval/eval_set.json

The ``retrieve_fn`` is injectable so the orchestration is testable without a key.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Callable, Optional

from backend.eval.metrics import EvalCase, EvalReport, build_report

logger = logging.getLogger(__name__)

_DEFAULT_SET = Path(__file__).parent / "eval_set.json"


def load_eval_set(path: Path) -> list[EvalCase]:
    data = json.loads(Path(path).read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    return [EvalCase.from_dict(c) for c in cases]


def run_eval(
    cases: list[EvalCase],
    retrieve_fn: Optional[Callable] = None,
    top_k: int = 5,
    ks: tuple[int, ...] = (1, 3, 5),
) -> EvalReport:
    """Run the retriever over every case and score the results.

    ``retrieve_fn(query, top_k, ticker, year, document_type) -> list`` defaults
    to ``backend.retrieval.retriever.retrieve``. We pass the case's known ticker/
    year/doc_type as explicit filters so the eval measures ranking quality given
    correct scoping, not the filter-extraction step (tested separately).
    """
    if retrieve_fn is None:
        from backend.retrieval.retriever import retrieve as retrieve_fn  # noqa: PLC0415

    retrieved_per_case = []
    for case in cases:
        retrieved = retrieve_fn(
            query=case.query,
            top_k=top_k,
            ticker=case.ticker,
            year=case.year,
            document_type=case.doc_type,
        )
        retrieved_per_case.append(retrieved)
    return build_report(cases, retrieved_per_case, ks=ks)


def format_report(report: EvalReport) -> str:
    lines = ["", "Retrieval eval", "=" * 40]
    for r in report.results:
        rank = r.rank if r.rank is not None else "—"
        lines.append(f"  rank={str(rank):>3}  {r.case.ticker:<6} {r.case.query[:54]}")
    lines.append("-" * 40)
    s = report.summary()
    lines.append(
        f"  n={s['n']}  MRR={s['mrr']}  "
        + "  ".join(f"hit@{k}={s[f'hit@{k}']}" for k in report.ks)
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="Run the retrieval eval harness.")
    parser.add_argument("--set", default=str(_DEFAULT_SET), help="path to eval set JSON")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    cases = load_eval_set(Path(args.set))
    if not cases:
        print("No eval cases found.")
        return 1
    report = run_eval(cases, top_k=args.top_k)
    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
