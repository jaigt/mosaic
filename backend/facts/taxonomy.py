"""Canonical line-item taxonomy: maps messy XBRL concepts to a controlled
vocabulary so figures are comparable across companies.

This is the crux of cross-company comparability and is meant to GROW over time —
add concepts as new filers surface variants. Each canonical key lists its XBRL
concepts in **priority order**: when a filing reports more than one of them for
the same period, the earliest-listed wins (so a specific revenue concept beats a
generic fallback). Keep it a pure data structure — no I/O.
"""
from __future__ import annotations

# statement bucket each canonical key belongs to
INCOME = "income_statement"
BALANCE = "balance_sheet"
CASHFLOW = "cash_flow"

# canonical_key -> (statement, [xbrl concepts in priority order])
# Concepts are matched WITHOUT the "us-gaap:"/"ifrs-full:" namespace prefix so a
# company using a different namespace for the same concept still maps.
TAXONOMY: dict[str, tuple[str, list[str]]] = {
    # ── Income statement ──────────────────────────────────────────────────
    "revenue": (INCOME, [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueNet",
    ]),
    "cost_of_revenue": (INCOME, [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ]),
    "gross_profit": (INCOME, ["GrossProfit"]),
    "operating_expenses": (INCOME, ["OperatingExpenses", "CostsAndExpenses"]),
    "rd_expense": (INCOME, ["ResearchAndDevelopmentExpense"]),
    "sga_expense": (INCOME, [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ]),
    "operating_income": (INCOME, ["OperatingIncomeLoss"]),
    "interest_expense": (INCOME, ["InterestExpense", "InterestExpenseNonoperating"]),
    "pretax_income": (INCOME, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ]),
    "income_tax": (INCOME, ["IncomeTaxExpenseBenefit"]),
    "net_income": (INCOME, [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ]),
    "eps_basic": (INCOME, ["EarningsPerShareBasic"]),
    "eps_diluted": (INCOME, ["EarningsPerShareDiluted"]),
    "shares_basic": (INCOME, ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "shares_diluted": (INCOME, ["WeightedAverageNumberOfDilutedSharesOutstanding"]),

    # ── Balance sheet (instant) ───────────────────────────────────────────
    "total_assets": (BALANCE, ["Assets"]),
    "current_assets": (BALANCE, ["AssetsCurrent"]),
    "cash_and_equivalents": (BALANCE, ["CashAndCashEquivalentsAtCarryingValue"]),
    "short_term_investments": (BALANCE, ["ShortTermInvestments", "MarketableSecuritiesCurrent"]),
    "total_liabilities": (BALANCE, ["Liabilities"]),
    "current_liabilities": (BALANCE, ["LiabilitiesCurrent"]),
    "long_term_debt": (BALANCE, ["LongTermDebtNoncurrent", "LongTermDebt"]),
    "short_term_debt": (BALANCE, ["LongTermDebtCurrent", "DebtCurrent"]),
    "total_equity": (BALANCE, [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ]),
    "shares_outstanding": (BALANCE, ["CommonStockSharesOutstanding"]),

    # ── Cash flow (duration) ──────────────────────────────────────────────
    "operating_cash_flow": (CASHFLOW, [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ]),
    "capex": (CASHFLOW, [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ]),
    "depreciation_amortization": (CASHFLOW, [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ]),
    "dividends_paid": (CASHFLOW, ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "stock_repurchases": (CASHFLOW, ["PaymentsForRepurchaseOfCommonStock"]),
}


def _strip_ns(concept: str) -> str:
    """Drop the namespace prefix: 'us-gaap:Revenues' -> 'Revenues'."""
    return concept.split(":", 1)[-1] if ":" in concept else concept


# Reverse index: bare concept -> (canonical_key, statement, priority). Built once.
_CONCEPT_INDEX: dict[str, tuple[str, str, int]] = {}
for _key, (_stmt, _concepts) in TAXONOMY.items():
    for _priority, _concept in enumerate(_concepts):
        # First mapping for a concept wins (a concept should map to one key).
        _CONCEPT_INDEX.setdefault(_strip_ns(_concept), (_key, _stmt, _priority))


def map_concept(concept: str) -> tuple[str, str, int] | None:
    """Map an XBRL concept tag to ``(canonical_key, statement, priority)``.

    Namespace-insensitive. Returns ``None`` for concepts not in the taxonomy
    (i.e. line items we don't track yet)."""
    return _CONCEPT_INDEX.get(_strip_ns(concept))


# Canonical keys whose natural unit is shares or per-share (not currency) — used
# when sanity-checking units and computing per-share metrics downstream.
PER_SHARE_KEYS = frozenset({"eps_basic", "eps_diluted"})
SHARE_COUNT_KEYS = frozenset({"shares_basic", "shares_diluted", "shares_outstanding"})
