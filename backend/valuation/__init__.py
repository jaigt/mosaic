"""Deterministic valuation engine over the structured fact base.

Pure metric/valuation math (`engine`) + an injectable market-price layer
(`prices`). The LLM narrates these numbers; it never computes them.
See docs/VALUATION_ENGINE_DESIGN.md."""
from backend.valuation.engine import (
    DCFAssumptions,
    compute_metrics,
    compute_valuation,
)
from backend.valuation.prices import get_price_snapshot, get_price_history
from backend.valuation.thesis import derive_signals, format_thesis

__all__ = [
    "compute_metrics",
    "compute_valuation",
    "DCFAssumptions",
    "get_price_snapshot",
    "get_price_history",
    "derive_signals",
    "format_thesis",
]
