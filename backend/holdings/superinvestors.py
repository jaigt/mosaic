"""Smart-money tracker — "which tracked superinvestor funds hold ticker X".

EDGAR has no global "who holds X" reverse-index, and that's fine: for value
investing you want the NOTABLE holders, not all ~5k filers. So we track a curated
universe of superinvestor 13F filers (see ``funds.json``), pull each fund's two
most recent 13Fs (current + prior, for Q/Q change), and build a local index keyed
by ticker. Per-ticker queries then read the cached index instantly.

  refresh(registry)  ──fetch 2x13F/fund──▶  rows  ──save_index──▶  cache JSON
  funds_holding(tk)  ──load_index──▶  filter+rank  ──▶  TickerOwnership

The change/index logic is PURE + unit-tested; the EDGAR fetch is isolated in
``refresh`` with an injectable company resolver. EDGAR-only — no API key/quota.
"""
import datetime
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from backend.config import settings
from backend.holdings.institutions import _num, _records_from_infotable
from backend.holdings.models import FundPosition, TickerOwnership

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "funds.json"
# Index cache lives under the (gitignored) data cache dir, beside lancedb.
_INDEX_PATH = Path(settings.lancedb_path).parent / "cache" / "smart_money_index.json"


def load_registry(path: Optional[Path] = None) -> list:
    """Load the curated fund list [{name, cik}, ...]."""
    p = Path(path) if path else _REGISTRY_PATH
    data = json.loads(p.read_text())
    return [f for f in data.get("funds", []) if f.get("cik")]


def classify_change(cur_shares: float, prev_shares: float) -> str:
    """Q/Q position-change label. PURE."""
    if prev_shares <= 0 and cur_shares > 0:
        return "new"
    if cur_shares <= 0 and prev_shares > 0:
        return "exited"
    if cur_shares > prev_shares:
        return "added"
    if cur_shares < prev_shares:
        return "trimmed"
    return "unchanged"


def _clean_ticker(v) -> Optional[str]:
    """Coerce a possibly-NaN/float/None ticker to an uppercase string or None.
    (13F infotables carry NaN for holdings without a resolved ticker.)"""
    if not isinstance(v, str):
        return None
    v = v.strip().upper()
    return v or None


def _key(rec: dict) -> str:
    return (rec.get("cusip") or rec.get("ticker") or rec.get("issuer") or "?")


def build_fund_rows(fund: str, cik: str, as_of: str, current: list, prior: list) -> list:
    """Build per-position rows for one fund, tagged with Q/Q change. PURE.

    ``current``/``prior`` are normalized holding dicts {issuer,ticker,cusip,value,
    shares}. Positions in current get new/added/trimmed/unchanged; positions only
    in prior get an ``exited`` row (shares=0). Merges duplicate rows by key.
    """
    def merge(records: list) -> dict:
        out: dict = {}
        for r in records:
            k = _key(r)
            cur = out.get(k)
            if cur is None:
                out[k] = {
                    "issuer": str(r.get("issuer") or ""), "ticker": _clean_ticker(r.get("ticker")),
                    "cusip": str(r.get("cusip") or ""), "value": _num(r.get("value")),
                    "shares": _num(r.get("shares")),
                }
            else:
                cur["value"] += _num(r.get("value"))
                cur["shares"] += _num(r.get("shares"))
        return out

    cur_map = merge(current)
    prior_map = merge(prior)
    total_value = sum(h["value"] for h in cur_map.values()) or 0.0

    rows: list = []
    for k, h in cur_map.items():
        prev_shares = prior_map.get(k, {}).get("shares", 0.0)
        rows.append(FundPosition(
            fund=fund, cik=cik, ticker=(h["ticker"] or None), issuer=h["issuer"],
            value=h["value"], shares=h["shares"],
            pct=round(h["value"] / total_value * 100.0, 2) if total_value else 0.0,
            as_of=as_of, change=classify_change(h["shares"], prev_shares),
            prev_shares=prev_shares,
        ).to_dict())
    # Exited positions (held prior, gone now).
    for k, h in prior_map.items():
        if k not in cur_map and h["shares"] > 0:
            rows.append(FundPosition(
                fund=fund, cik=cik, ticker=(h["ticker"] or None), issuer=h["issuer"],
                value=0.0, shares=0.0, pct=0.0, as_of=as_of,
                change="exited", prev_shares=h["shares"],
            ).to_dict())
    return rows


def funds_holding_from_rows(ticker: str, rows: list, refreshed_at: str = "") -> TickerOwnership:
    """Filter index rows for ``ticker`` into a TickerOwnership. PURE."""
    tk = ticker.strip().upper()
    holders, exits = [], []
    for r in rows:
        if (_clean_ticker(r.get("ticker")) or "") != tk:
            continue
        pos = FundPosition(
            fund=r["fund"], cik=r["cik"], ticker=r.get("ticker"), issuer=r.get("issuer", ""),
            value=_num(r.get("value")), shares=_num(r.get("shares")),
            pct=_num(r.get("pct")), as_of=r.get("as_of", ""),
            change=r.get("change", ""), prev_shares=_num(r.get("prev_shares")),
        )
        (exits if pos.change == "exited" else holders).append(pos)
    holders.sort(key=lambda p: p.value, reverse=True)
    return TickerOwnership(ticker=tk, refreshed_at=refreshed_at, positions=holders, exits=exits)


# ── persistence ───────────────────────────────────────────────────────────────

def save_index(rows: list, path: Optional[Path] = None) -> Path:
    p = Path(path) if path else _INDEX_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "funds": len({r["cik"] for r in rows}), "rows": rows}
    p.write_text(json.dumps(payload))
    return p


def load_index(path: Optional[Path] = None) -> dict:
    p = Path(path) if path else _INDEX_PATH
    if not p.exists():
        return {"refreshed_at": "", "funds": 0, "rows": []}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"smart-money index unreadable: {e}")
        return {"refreshed_at": "", "funds": 0, "rows": []}


# ── live refresh + query ──────────────────────────────────────────────────────

def _latest_two_13f(company):
    """Return (current_obj, prior_obj|None) for a fund's two most recent 13F-HR."""
    filings = company.get_filings(form="13F-HR")
    flist = list(filings) if filings is not None else []
    if not flist:
        return None, None
    cur = flist[0].obj()
    prior = flist[1].obj() if len(flist) > 1 else None
    return cur, prior


def refresh(
    registry: Optional[list] = None,
    company_fn: Optional[Callable] = None,
    save: bool = True,
    index_path: Optional[Path] = None,
) -> dict:
    """Fetch each tracked fund's latest+prior 13F, build the ticker index, cache it.

    Returns {"funds": n, "rows": m, "errors": [...]}. ``company_fn`` injectable.
    """
    if registry is None:
        registry = load_registry()
    if company_fn is None:
        from edgar import Company  # noqa: PLC0415
        company_fn = Company

    rows: list = []
    errors: list = []
    ok_funds = 0
    for fund in registry:
        name, cik = fund.get("name", fund.get("cik")), str(fund.get("cik"))
        try:
            cur, prior = _latest_two_13f(company_fn(cik))
            if cur is None:
                errors.append(f"{name}: no 13F")
                continue
            as_of = str(getattr(cur, "report_period", "") or "")
            cur_records = _records_from_infotable(cur)
            prior_records = _records_from_infotable(prior) if prior is not None else []
            rows.extend(build_fund_rows(name, cik, as_of, cur_records, prior_records))
            ok_funds += 1
        except Exception as e:  # noqa: BLE001 — skip a bad fund, keep the rest
            errors.append(f"{name}: {e}")
            logger.warning(f"smart-money refresh failed for {name}: {e}")

    if save:
        save_index(rows, index_path)
    return {"funds": ok_funds, "rows": len(rows), "errors": errors}


def funds_holding(ticker: str, index_path: Optional[Path] = None) -> TickerOwnership:
    """Query the cached index for tracked funds holding ``ticker``."""
    idx = load_index(index_path)
    return funds_holding_from_rows(ticker, idx.get("rows", []), idx.get("refreshed_at", ""))


def index_is_stale(refreshed_at: str, stale_days: int = 30, now: Optional[datetime.datetime] = None) -> bool:
    """Whether the index should be rebuilt. PURE. Missing/unparseable → stale."""
    if not refreshed_at:
        return True
    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        ts = datetime.datetime.strptime(refreshed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except Exception:
        return True
    return (now - ts).days >= stale_days
