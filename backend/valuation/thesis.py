"""Deterministic investment-thesis scaffolding.

Turns the structured metrics + valuation into labeled, evidence-backed bull/bear
**signals** using explicit heuristic rules — so the thesis skeleton is consistent
and traceable rather than ad-hoc LLM judgment. The model then narrates these and
layers in qualitative context (moat, risks). Pure; no I/O, no LLM.

The thresholds are deliberately simple and conservative; they're a starting
framework a user can argue with, not a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Signal:
    dimension: str   # profitability | returns | cash_flow | balance_sheet | growth | valuation
    direction: str   # "bull" | "bear" | "neutral"
    label: str       # short headline
    detail: str      # the supporting number


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def derive_signals(metrics: dict, valuation: dict) -> list[Signal]:
    """Apply heuristic rules to the latest metrics + valuation → signals. PURE."""
    out: list[Signal] = []
    lp = metrics.get("latest_period")
    pm = metrics.get("per_period", {}).get(lp, {}) if lp else {}
    t = metrics.get("trends", {})

    def add(dim, direction, label, detail):
        out.append(Signal(dim, direction, label, detail))

    nm = pm.get("net_margin")
    if nm is not None:
        if nm >= 0.15: add("profitability", "bull", "High net margin", f"net margin {_pct(nm)}")
        elif nm < 0.05: add("profitability", "bear", "Thin net margin", f"net margin {_pct(nm)}")

    roic = pm.get("roic_approx")
    if roic is not None:
        if roic >= 0.15: add("returns", "bull", "Strong returns on capital", f"ROIC≈ {_pct(roic)}")
        elif roic < 0.08: add("returns", "bear", "Low returns on capital", f"ROIC≈ {_pct(roic)}")

    fm = pm.get("fcf_margin")
    if fm is not None:
        if fm >= 0.10: add("cash_flow", "bull", "Strong free cash flow", f"FCF margin {_pct(fm)}")
        elif fm < 0: add("cash_flow", "bear", "Burning cash", f"FCF margin {_pct(fm)}")

    nde = pm.get("net_debt_to_ebitda")
    if nde is not None:
        if nde <= 1.0: add("balance_sheet", "bull", "Low leverage", f"net debt/EBITDA {nde:.1f}x")
        elif nde > 3.0: add("balance_sheet", "bear", "Elevated leverage", f"net debt/EBITDA {nde:.1f}x")
    cr = pm.get("current_ratio")
    if cr is not None and cr < 1.0:
        add("balance_sheet", "neutral", "Current ratio below 1", f"current ratio {cr:.2f}x")

    rg, rc = t.get("revenue_growth_yoy"), t.get("revenue_cagr")
    if rg is not None:
        if rg >= 0.10: add("growth", "bull", "Double-digit revenue growth", f"revenue +{_pct(rg)} YoY")
        elif rg < 0: add("growth", "bear", "Revenue declining", f"revenue {_pct(rg)} YoY")
        elif rg < 0.03: add("growth", "neutral", "Slow revenue growth", f"revenue +{_pct(rg)} YoY")
    if rg is not None and rc is not None and rc > 0 and rg < rc - 0.02:
        add("growth", "bear", "Decelerating growth", f"YoY {_pct(rg)} below {_pct(rc)} CAGR")

    dcf = valuation.get("dcf")
    if dcf and dcf.get("upside_vs_price") is not None:
        up = dcf["upside_vs_price"]
        if up >= 0.20: add("valuation", "bull", "Trades below DCF value", f"~{up*100:.0f}% upside to intrinsic")
        elif up <= -0.20: add("valuation", "bear", "Trades above DCF value", f"~{-up*100:.0f}% above intrinsic")
    fy = (valuation.get("multiples") or {}).get("fcf_yield")
    if fy is not None and fy < 0.03:
        add("valuation", "bear", "Low FCF yield", f"FCF yield {_pct(fy)}")
    return out


# What-would-change-the-view templates, keyed on a bear signal's dimension.
_WATCH = {
    "valuation": "a pullback toward the DCF range, or growth/margins coming in materially above the assumptions",
    "growth": "a return to double-digit revenue growth (or stabilization if declining)",
    "balance_sheet": "deleveraging back below ~3x net debt/EBITDA",
    "profitability": "net margin recovering above ~10%",
    "cash_flow": "a return to positive, sustained free cash flow",
    "returns": "ROIC improving back above ~10%",
}


def format_thesis(ticker: str, metrics: dict, valuation: dict, signals: list[Signal]) -> str:
    """Render the deterministic thesis scaffold the LLM will narrate. PURE."""
    bull = [s for s in signals if s.direction == "bull"]
    bear = [s for s in signals if s.direction == "bear"]
    neutral = [s for s in signals if s.direction == "neutral"]
    lp = metrics.get("latest_period")

    lines = [f"{ticker} — investment thesis scaffold (heuristic signals on filed numbers, latest {lp}):"]
    lines.append("BULL:")
    lines += [f"  + {s.label} ({s.detail})" for s in bull] or ["  (none flagged)"]
    lines.append("BEAR:")
    lines += [f"  - {s.label} ({s.detail})" for s in bear] or ["  (none flagged)"]
    if neutral:
        lines.append("WATCH:")
        lines += [f"  · {s.label} ({s.detail})" for s in neutral]

    dcf = valuation.get("dcf")
    if dcf:
        verdict = ("below" if (dcf.get("upside_vs_price") or 0) > 0 else "above")
        price = valuation.get("price")
        pstr = f"price ${price:.2f}, " if price is not None else ""
        lines.append(
            f"VALUATION: {pstr}DCF intrinsic ${dcf['intrinsic_value_per_share']:.2f} "
            f"(range ${dcf['range_low']:.2f}–${dcf['range_high']:.2f}) — trading {verdict} the DCF estimate.")

    # "What would change the view": one item per distinct bear dimension (max 3).
    seen, watch = set(), []
    for s in bear:
        if s.dimension not in seen and s.dimension in _WATCH:
            seen.add(s.dimension)
            watch.append(_WATCH[s.dimension])
        if len(watch) >= 3:
            break
    if not watch and bull:
        watch = ["erosion of the bull-case drivers above (margins, growth, or returns weakening)"]
    if watch:
        lines.append("WHAT WOULD CHANGE THE VIEW:")
        lines += [f"  • {w}" for w in watch]

    lines.append("(Heuristic flags on filed figures — qualitative context (moat, risks) and the "
                 "final judgment are layered on top; not investment advice.)")
    return "\n".join(lines)
