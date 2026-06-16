"""Deterministic valuation engine.

Pure functions over the structured fact base (`facts.store.get_financials`
output). The LLM never computes these numbers — it narrates them. Every metric
returns ``None`` when its inputs are missing (we never fabricate a figure).

Two layers:
- :func:`compute_metrics` — margins, returns, leverage, FCF, and growth trends.
  No price needed.
- :func:`compute_valuation` — multiples + a transparent DCF scaffold. Needs a
  price + share count (injected; see ``valuation.prices``). Assumptions are
  explicit and overridable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

Financials = dict  # the get_financials() return shape


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def by_period(fin: Financials) -> dict[str, dict[str, float]]:
    """Pivot get_financials() into ``{period_end: {canonical_key: value}}``."""
    out: dict[str, dict[str, float]] = {}
    for key, rows in (fin.get("metrics") or {}).items():
        for r in rows:
            out.setdefault(r["period_end"], {})[key] = r["value"]
    return out


def _periods_desc(pivot: dict[str, dict[str, float]]) -> list[str]:
    return sorted(pivot.keys(), reverse=True)


def _net_debt(p: dict[str, float]) -> Optional[float]:
    debt = sum(v for k in ("long_term_debt", "short_term_debt")
               if (v := p.get(k)) is not None)
    cash = sum(v for k in ("cash_and_equivalents", "short_term_investments")
               if (v := p.get(k)) is not None)
    if not any(p.get(k) is not None for k in ("long_term_debt", "short_term_debt")):
        return None
    return debt - cash


def _ebitda(p: dict[str, float]) -> Optional[float]:
    oi, da = p.get("operating_income"), p.get("depreciation_amortization")
    if oi is None:
        return None
    return oi + (da or 0.0)  # D&A optional; approximates EBITDA from operating income


def _fcf(p: dict[str, float]) -> Optional[float]:
    ocf, capex = p.get("operating_cash_flow"), p.get("capex")
    if ocf is None or capex is None:
        return None
    return ocf - capex  # capex is reported as a positive outflow


def metrics_for_period(p: dict[str, float]) -> dict[str, Optional[float]]:
    """Derived metrics for one period's ``{canonical_key: value}``."""
    rev = p.get("revenue")
    fcf = _fcf(p)
    ebitda = _ebitda(p)
    nd = _net_debt(p)
    tax_rate = _safe_div(p.get("income_tax"), p.get("pretax_income"))
    nopat = (p["operating_income"] * (1 - tax_rate)
             if p.get("operating_income") is not None and tax_rate is not None else None)
    invested_capital = None
    if p.get("total_equity") is not None and nd is not None:
        invested_capital = p["total_equity"] + max(nd, 0.0)
    return {
        "gross_margin": _safe_div(p.get("gross_profit"), rev),
        "operating_margin": _safe_div(p.get("operating_income"), rev),
        "net_margin": _safe_div(p.get("net_income"), rev),
        "fcf": fcf,
        "fcf_margin": _safe_div(fcf, rev),
        "ebitda": ebitda,
        "ebitda_margin": _safe_div(ebitda, rev),
        "roe": _safe_div(p.get("net_income"), p.get("total_equity")),
        "roa": _safe_div(p.get("net_income"), p.get("total_assets")),
        "roic_approx": _safe_div(nopat, invested_capital),
        "net_debt": nd,
        "net_debt_to_ebitda": _safe_div(nd, ebitda),
        "current_ratio": _safe_div(p.get("current_assets"), p.get("current_liabilities")),
        "interest_coverage": _safe_div(p.get("operating_income"), p.get("interest_expense")),
        "effective_tax_rate": tax_rate,
    }


def _cagr(first: float, last: float, years: int) -> Optional[float]:
    if years <= 0 or first is None or last is None or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def compute_metrics(fin: Financials) -> dict:
    """Per-period derived metrics + growth trends. Pure; no price required."""
    pivot = by_period(fin)
    periods = _periods_desc(pivot)
    per_period = {pe: metrics_for_period(pivot[pe]) for pe in periods}

    def series(key: str) -> list[tuple[str, float]]:
        return [(pe, pivot[pe][key]) for pe in periods if key in pivot[pe]]

    trends: dict[str, Optional[float]] = {}
    for key in ("revenue", "net_income", "operating_income"):
        s = series(key)  # newest first
        if len(s) >= 2:
            trends[f"{key}_growth_yoy"] = _safe_div(s[0][1] - s[1][1], abs(s[1][1]))
        if len(s) >= 2:
            # oldest→newest CAGR across the available span
            trends[f"{key}_cagr"] = _cagr(s[-1][1], s[0][1], len(s) - 1)

    return {
        "ticker": fin.get("ticker"),
        "latest_period": periods[0] if periods else None,
        "periods": periods,
        "per_period": per_period,
        "trends": trends,
    }


# ── Valuation (needs a price + share count) ───────────────────────────────────

@dataclass(frozen=True)
class DCFAssumptions:
    """Explicit, user-overridable DCF inputs. Defaults are deliberately generic;
    surface them to the user rather than hiding them."""
    years: int = 5
    growth: Optional[float] = None     # None → derive from revenue CAGR (clamped)
    discount_rate: float = 0.09        # WACC proxy
    terminal_growth: float = 0.025

    def resolved_growth(self, fallback: Optional[float]) -> float:
        g = self.growth if self.growth is not None else (fallback if fallback is not None else 0.04)
        return max(min(g, 0.20), -0.05)  # clamp to a sane band


def _dcf(fcf0: float, shares: float, net_debt: float, a: DCFAssumptions,
         growth: float) -> Optional[float]:
    if fcf0 is None or fcf0 <= 0 or shares is None or shares <= 0:
        return None
    pv = 0.0
    fcf = fcf0
    for t in range(1, a.years + 1):
        fcf *= (1 + growth)
        pv += fcf / ((1 + a.discount_rate) ** t)
    if a.discount_rate <= a.terminal_growth:
        return None
    terminal = fcf * (1 + a.terminal_growth) / (a.discount_rate - a.terminal_growth)
    pv += terminal / ((1 + a.discount_rate) ** a.years)
    equity = pv - (net_debt or 0.0)
    return equity / shares


def compute_valuation(
    fin: Financials,
    price: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    assumptions: Optional[DCFAssumptions] = None,
) -> dict:
    """Multiples (if ``price`` given) + a transparent DCF intrinsic-value range.

    ``shares_outstanding`` falls back to the latest stored share count. Returns
    a dict with the assumptions echoed back, so the user always sees the inputs.
    """
    m = compute_metrics(fin)
    pivot = by_period(fin)
    latest = pivot.get(m["latest_period"], {}) if m["latest_period"] else {}
    lm = m["per_period"].get(m["latest_period"], {}) if m["latest_period"] else {}

    shares = shares_outstanding or latest.get("shares_outstanding") or latest.get("shares_diluted")
    net_debt = lm.get("net_debt")
    fcf = lm.get("fcf")
    ebitda = lm.get("ebitda")

    out: dict = {"ticker": fin.get("ticker"), "latest_period": m["latest_period"],
                 "price": price, "shares_outstanding": shares, "multiples": {}, "dcf": None}

    if price is not None and shares:
        mkt_cap = price * shares
        ev = mkt_cap + (net_debt or 0.0)
        out["multiples"] = {
            "market_cap": mkt_cap,
            "enterprise_value": ev,
            "pe": _safe_div(mkt_cap, latest.get("net_income")),
            "ev_ebitda": _safe_div(ev, ebitda),
            "p_fcf": _safe_div(mkt_cap, fcf),
            "p_s": _safe_div(mkt_cap, latest.get("revenue")),
            "fcf_yield": _safe_div(fcf, mkt_cap),
        }

    a = assumptions or DCFAssumptions()
    growth = a.resolved_growth(m["trends"].get("revenue_cagr"))
    base = _dcf(fcf, shares, net_debt, a, growth) if fcf and shares else None
    if base is not None:
        low = _dcf(fcf, shares, net_debt, a, max(growth - 0.03, -0.05))
        high = _dcf(fcf, shares, net_debt, a, min(growth + 0.03, 0.20))
        out["dcf"] = {
            "intrinsic_value_per_share": base,
            "range_low": low,
            "range_high": high,
            "assumptions": {
                "years": a.years, "growth": growth,
                "discount_rate": a.discount_rate, "terminal_growth": a.terminal_growth,
            },
            "upside_vs_price": _safe_div(base - price, price) if price else None,
        }
    return out
