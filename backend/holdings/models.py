"""Data models for the holdings trackers (Form 4 insider trades, 13F holdings).

Kept here (not in models/schemas.py) so the holdings feature is self-contained.
All carry ``to_dict`` for the API and ``summary_text`` for the agent tool.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InsiderTxn:
    insider: str
    position: str
    date: str
    txn_type: str            # "buy" | "sell" | "other"
    code: str                # SEC transaction code (P, S, A, G, M, F, ...)
    description: str
    shares: float
    price: Optional[float]
    value: Optional[float]

    def to_dict(self) -> dict:
        return {
            "insider": self.insider, "position": self.position, "date": self.date,
            "txn_type": self.txn_type, "code": self.code, "description": self.description,
            "shares": self.shares, "price": self.price, "value": self.value,
        }


@dataclass
class InsiderActivity:
    ticker: str
    transactions: list = field(default_factory=list)   # list[InsiderTxn]
    buys: int = 0                # count of open-market purchase rows
    sells: int = 0               # count of open-market sale rows
    bought_shares: float = 0.0
    sold_shares: float = 0.0

    @property
    def net_shares(self) -> float:
        return self.bought_shares - self.sold_shares

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "transactions": [t.to_dict() for t in self.transactions],
            "buys": self.buys, "sells": self.sells,
            "bought_shares": self.bought_shares, "sold_shares": self.sold_shares,
            "net_shares": self.net_shares,
        }

    def summary_text(self, top: int = 8) -> str:
        """Compact text for the agent's observation."""
        if not self.transactions:
            return f"No recent insider (Form 4) transactions found for {self.ticker}."
        head = (
            f"{self.ticker} insider activity (recent Form 4s): "
            f"{self.buys} open-market buys ({self.bought_shares:,.0f} sh), "
            f"{self.sells} sells ({self.sold_shares:,.0f} sh), "
            f"net {self.net_shares:,.0f} sh."
        )
        lines = []
        for t in self.transactions[:top]:
            px = f" @ ${t.price:,.2f}" if t.price else ""
            lines.append(f"  {t.date} {t.insider} ({t.position}) {t.txn_type.upper()} {t.shares:,.0f} sh{px} [{t.description}]")
        return head + "\n" + "\n".join(lines)


@dataclass
class Holding:
    issuer: str
    ticker: Optional[str]
    cusip: str
    value: float             # USD market value reported
    shares: float
    pct: float               # % of the fund's reported portfolio value

    def to_dict(self) -> dict:
        return {
            "issuer": self.issuer, "ticker": self.ticker, "cusip": self.cusip,
            "value": self.value, "shares": self.shares, "pct": self.pct,
        }


@dataclass
class FundHoldings:
    fund: str
    report_period: str
    total_value: float
    total_holdings: int
    holdings: list = field(default_factory=list)   # top-N list[Holding] by value

    def to_dict(self) -> dict:
        return {
            "fund": self.fund, "report_period": self.report_period,
            "total_value": self.total_value, "total_holdings": self.total_holdings,
            "holdings": [h.to_dict() for h in self.holdings],
        }

    def summary_text(self, top: int = 10) -> str:
        if not self.holdings:
            return f"No 13F holdings found for '{self.fund}'."
        head = (
            f"{self.fund} 13F holdings as of {self.report_period}: "
            f"{self.total_holdings} positions, ${self.total_value:,.0f} total. Top holdings:"
        )
        lines = [
            f"  {h.ticker or h.issuer}: ${h.value:,.0f} ({h.pct:.1f}%)"
            for h in self.holdings[:top]
        ]
        return head + "\n" + "\n".join(lines)
