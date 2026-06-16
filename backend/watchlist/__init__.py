"""Watchlist — a saved set of tickers with an on-demand dashboard that runs the
valuation engine + signals across them and surfaces what changed since last view.
See docs/VALUATION_ENGINE_DESIGN.md (watchlist/alerts layer)."""
from backend.watchlist.store import (
    add_ticker,
    list_tickers,
    remove_ticker,
)
from backend.watchlist.dashboard import build_dashboard, build_row

__all__ = ["add_ticker", "remove_ticker", "list_tickers", "build_dashboard", "build_row"]
