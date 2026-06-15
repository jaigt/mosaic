"""Offline retrieval evaluation: labelled query set + pure scorer + live runner.

See ``harness.py`` to run, ``metrics.py`` for the pure scoring functions.
"""
from backend.eval.metrics import (
    EvalCase,
    EvalReport,
    build_report,
    case_matches,
    hit_at_k,
    rank_of_first_match,
    reciprocal_rank,
    score_case,
)

__all__ = [
    "EvalCase",
    "EvalReport",
    "build_report",
    "case_matches",
    "hit_at_k",
    "rank_of_first_match",
    "reciprocal_rank",
    "score_case",
]
