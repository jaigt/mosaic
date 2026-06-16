"""Pure formatters turning the fact base + valuation output into compact,
authoritative text for the agent's evidence set (and the citation panel).

Numbers here come from XBRL filings (deterministic), so the synthesis model
should treat them as ground truth rather than re-deriving figures from prose.
"""
from __future__ import annotations

from typing import Optional


def _money(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.1f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _x(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.1f}x"


def format_fundamentals(fin: dict, metrics: dict) -> str:
    """Compact fundamentals + ratios for the latest period, plus growth. PURE."""
    ticker = fin.get("ticker") or metrics.get("ticker") or "?"
    lp = metrics.get("latest_period")
    if not lp:
        return f"No structured financials available for {ticker}."
    pivot = {k: rows[0]["value"] for k, rows in fin.get("metrics", {}).items() if rows}
    pm = metrics["per_period"].get(lp, {})
    t = metrics.get("trends", {})

    lines = [
        f"{ticker} — structured financials (from XBRL filings), latest period {lp}:",
        f"  Revenue {_money(pivot.get('revenue'))} | Net income {_money(pivot.get('net_income'))} | "
        f"FCF {_money(pm.get('fcf'))} | EBITDA {_money(pm.get('ebitda'))}",
        f"  Margins — gross {_pct(pm.get('gross_margin'))}, operating {_pct(pm.get('operating_margin'))}, "
        f"net {_pct(pm.get('net_margin'))}, FCF {_pct(pm.get('fcf_margin'))}",
        f"  Returns — ROE {_pct(pm.get('roe'))}, ROA {_pct(pm.get('roa'))}, ROIC≈ {_pct(pm.get('roic_approx'))}",
        f"  Balance — net debt {_money(pm.get('net_debt'))}, net-debt/EBITDA {_x(pm.get('net_debt_to_ebitda'))}, "
        f"current ratio {_x(pm.get('current_ratio'))}",
        f"  Growth — revenue YoY {_pct(t.get('revenue_growth_yoy'))}, revenue CAGR {_pct(t.get('revenue_cagr'))}, "
        f"net income YoY {_pct(t.get('net_income_growth_yoy'))}",
    ]
    hist = fin.get("metrics", {}).get("revenue", [])
    if len(hist) > 1:
        lines.append("  Revenue history — " + ", ".join(
            f"{r['fiscal_year']}: {_money(r['value'])}" for r in hist[:4]))
    return "\n".join(lines)


def format_segments(seg: dict, max_members: int = 6) -> str:
    """Revenue broken down by each reported axis (geography, product, …). PURE.
    Returns '' when there are no segment facts."""
    axes = seg.get("axes") or {}
    if not axes:
        return ""
    lines = [f"Revenue by segment ({seg.get('period_end')}; as reported, may include subtotals):"]
    for axis, members in axes.items():
        top = members[:max_members]
        rendered = ", ".join(f"{m['member']} {_money(m['value'])}" for m in top)
        more = f" (+{len(members) - len(top)} more)" if len(members) > len(top) else ""
        lines.append(f"  {axis}: {rendered}{more}")
    return "\n".join(lines)


def format_valuation(val: dict) -> str:
    """Multiples + DCF summary, with assumptions stated. PURE."""
    ticker = val.get("ticker") or "?"
    mult = val.get("multiples") or {}
    dcf = val.get("dcf")
    lines = [f"{ticker} — valuation (latest period {val.get('latest_period')}):"]
    if val.get("price") is not None:
        lines.append(f"  Price ${val['price']:.2f} | Market cap {_money(mult.get('market_cap'))} | "
                     f"EV {_money(mult.get('enterprise_value'))}")
        lines.append(f"  Multiples — P/E {_x(mult.get('pe'))}, EV/EBITDA {_x(mult.get('ev_ebitda'))}, "
                     f"P/FCF {_x(mult.get('p_fcf'))}, P/S {_x(mult.get('p_s'))}, "
                     f"FCF yield {_pct(mult.get('fcf_yield'))}")
    else:
        lines.append("  Price unavailable — multiples skipped (fundamentals + DCF only).")
    if dcf:
        a = dcf["assumptions"]
        lines.append(
            f"  DCF intrinsic value ${dcf['intrinsic_value_per_share']:.2f}/share "
            f"(range ${dcf['range_low']:.2f}–${dcf['range_high']:.2f})")
        lines.append(
            f"  DCF assumptions — {a['years']}y, growth {_pct(a['growth'])}, "
            f"discount {_pct(a['discount_rate'])}, terminal {_pct(a['terminal_growth'])}"
            + (f"; upside vs price {_pct(dcf['upside_vs_price'])}" if dcf.get("upside_vs_price") is not None else ""))
        lines.append("  (DCF is a transparent scaffold on stated assumptions — not a recommendation.)")
    return "\n".join(lines)
