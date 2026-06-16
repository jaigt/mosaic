"""Deterministic sanity checks over a set of facts for one period.

These accounting identities catch extraction/mapping errors before a bad number
reaches a valuation — e.g. a segment value mistaken for a total, or a sign error.
A failed identity doesn't delete the fact; it lowers confidence and surfaces the
issue, so the data stays visible but flagged. Pure functions, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.facts.models import FinancialFact

# Relative tolerance for identity checks (filings round; allow ~1%).
_REL_TOL = 0.01


@dataclass(frozen=True)
class ValidationIssue:
    period_end: str
    rule: str
    detail: str


def _close(a: float, b: float) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= _REL_TOL * scale


def validate_period(facts: dict[str, float]) -> list[ValidationIssue]:
    """Check accounting identities for one period's ``{canonical_key: value}``.

    Each identity runs only if its inputs are present, so partial data doesn't
    spuriously flag. Returns the list of violations (empty = consistent)."""
    issues: list[ValidationIssue] = []
    g = facts.get

    def check(rule: str, lhs: float, rhs: float, detail: str) -> None:
        if not _close(lhs, rhs):
            issues.append(ValidationIssue(period_end="", rule=rule, detail=detail))

    if g("revenue") is not None and g("cost_of_revenue") is not None and g("gross_profit") is not None:
        check("gross_profit", g("revenue") - g("cost_of_revenue"), g("gross_profit"),
              f"revenue - cost_of_revenue = {g('revenue') - g('cost_of_revenue'):.0f} vs gross_profit {g('gross_profit'):.0f}")

    if g("total_assets") is not None and g("total_liabilities") is not None and g("total_equity") is not None:
        check("balance_sheet", g("total_liabilities") + g("total_equity"), g("total_assets"),
              f"liabilities + equity = {g('total_liabilities') + g('total_equity'):.0f} vs assets {g('total_assets'):.0f}")

    return issues


def flag_low_confidence(
    facts: list[FinancialFact], confidence: float = 0.5
) -> list[FinancialFact]:
    """Return copies of ``facts`` for periods that fail an identity, with reduced
    confidence. Facts in consistent periods are returned unchanged."""
    by_period: dict[str, dict[str, float]] = {}
    for f in facts:
        by_period.setdefault(f.period_end, {})[f.canonical_key] = f.value

    bad_periods = {
        period for period, vals in by_period.items() if validate_period(vals)
    }
    if not bad_periods:
        return facts

    out: list[FinancialFact] = []
    for f in facts:
        if f.period_end in bad_periods and f.confidence > confidence:
            out.append(FinancialFact(**{**f.__dict__, "confidence": confidence}))
        else:
            out.append(f)
    return out
