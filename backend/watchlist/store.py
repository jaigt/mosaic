"""SQLite store for the watchlist + per-ticker view snapshots.

Local, stdlib sqlite3 (own file, gitignored via data/*.db). The watchlist is the
user's saved tickers; snapshots hold the last-viewed key metrics per ticker so
the dashboard can show "what changed since you last looked" without a scheduler.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from backend.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker   TEXT PRIMARY KEY,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    ticker   TEXT PRIMARY KEY,
    taken_at TEXT,
    data     TEXT
);
"""


def _db_path() -> str:
    return getattr(settings, "watchlist_db_path", "./data/watchlist.db")


@contextmanager
def _connect():
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _norm(ticker: str) -> str:
    return (ticker or "").strip().upper()


def add_ticker(ticker: str) -> bool:
    """Add a ticker (idempotent). Returns False for an empty ticker."""
    t = _norm(ticker)
    if not t:
        return False
    from datetime import datetime, timezone
    with _connect() as conn:
        conn.execute(
            "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?) "
            "ON CONFLICT(ticker) DO NOTHING",
            (t, datetime.now(timezone.utc).isoformat()),
        )
    return True


def remove_ticker(ticker: str) -> None:
    t = _norm(ticker)
    with _connect() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (t,))
        conn.execute("DELETE FROM watchlist_snapshots WHERE ticker = ?", (t,))


def list_tickers() -> list[str]:
    with _connect() as conn:
        return [r["ticker"] for r in conn.execute(
            "SELECT ticker FROM watchlist ORDER BY ticker")]


def get_snapshot(ticker: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM watchlist_snapshots WHERE ticker = ?", (_norm(ticker),)
        ).fetchone()
    if not row or not row["data"]:
        return None
    try:
        return json.loads(row["data"])
    except Exception:  # noqa: BLE001
        return None


def save_snapshot(ticker: str, data: dict) -> None:
    from datetime import datetime, timezone
    with _connect() as conn:
        conn.execute(
            "INSERT INTO watchlist_snapshots (ticker, taken_at, data) VALUES (?, ?, ?) "
            "ON CONFLICT(ticker) DO UPDATE SET taken_at=excluded.taken_at, data=excluded.data",
            (_norm(ticker), datetime.now(timezone.utc).isoformat(), json.dumps(data)),
        )
