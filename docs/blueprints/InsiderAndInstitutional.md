# Blueprint: Insider Transactions & Institutional Holdings

> **Status:** Future work — not part of the core RAG pipeline.
> These are separate analytics layers that complement the 10-K/10-Q RAG system
> but operate on structured *transaction/position* data rather than narrative documents.

---

## Overview

`edgartools` already supports two SEC form types that are highly relevant to value
investing but currently unused in this project:

| Form | Filed by | Filed when | What it tells you |
|------|----------|------------|-------------------|
| **Form 4** | Corporate insiders (officers, directors, >10% owners) | Within 2 business days of a transaction | Insider buys/sells of company stock |
| **13F** | Institutional managers with >$100M AUM | 45 days after each quarter end | Full snapshot of a fund's equity holdings |

Both are available free from EDGAR, and `edgartools` parses them into structured
Python objects — no custom XML parsing required.

---

## Feature 1: Form 4 — Insider Transaction Tracker

### Why it matters

Insider *buying* at depressed prices is one of the strongest signals in value
investing. Executives have no reason to buy their own stock unless they believe
it is undervalued. Insider *selling* is noisier (diversification, taxes, options
vesting) but cluster-selling across multiple insiders is worth flagging.

### What you can build

- Per-ticker feed of recent insider transactions (buyer name, role, shares, price, date)
- Alerts when multiple insiders buy within the same 30-day window ("cluster buying")
- Historical chart of insider buy/sell ratio overlaid on stock price

### edgartools API sketch

```python
from edgar import Company

company = Company("AAPL")
form4_filings = company.get_filings(form="4")

for filing in form4_filings[:10]:
    f4 = filing.obj()              # edgartools parses Form 4 into a structured object
    for transaction in f4.transactions:
        print(
            transaction.reporting_owner,   # insider name
            transaction.relationship,      # "Director", "CEO", etc.
            transaction.transaction_date,
            transaction.shares,
            transaction.price_per_share,
            transaction.transaction_type,  # "P" = purchase, "S" = sale
        )
```

### Data model

```python
from pydantic import BaseModel
from typing import Literal
import datetime

class InsiderTransaction(BaseModel):
    ticker: str
    cik: str
    insider_name: str
    insider_role: str                          # "Director", "CFO", etc.
    transaction_date: datetime.date
    shares: float
    price_per_share: float
    transaction_type: Literal["purchase", "sale", "option_exercise", "gift"]
    is_direct_ownership: bool                  # direct vs. indirect (family trust, etc.)
    accession_number: str
```

### Integration considerations

- This is *not* a RAG use case — it's a structured query/alert use case. Store
  transactions in LanceDB or a simple SQLite table, then query with filters
  (`ticker="AAPL" AND transaction_type="purchase" AND date > 90 days ago`).
- Could surface in the UI as a "Recent Insider Activity" panel alongside the chat.
- SEC EDGAR enforces the same rate limits as 10-K fetching; use the same
  `_REQUEST_DELAY` from `edgar_fetcher.py`.

---

## Feature 2: 13F — Institutional Holdings Tracker

### Why it matters

Tracking what the best value investors (Berkshire Hathaway, Sequoia Fund, Pabrai
Funds, etc.) are buying and selling is a classic idea-generation technique.
A 13F tells you exactly which stocks a fund holds and how their position sizes
changed quarter-over-quarter.

### What you can build

- Snapshot of any fund's current holdings as a ranked table (position size, % of portfolio)
- Quarter-over-quarter diff: new positions, closed positions, increased/decreased
- "Smart money overlap" query: which stocks appear in the top 10 holdings of multiple
  funds you follow simultaneously?

### edgartools API sketch

```python
from edgar import Company

# Look up a fund by its CIK (Berkshire = 0001067983)
berkshire = Company("BRK-A")
filing_13f = berkshire.get_filings(form="13F-HR")[0]

holdings = filing_13f.obj()    # edgartools returns a ThirteenF object
for holding in holdings.infotable:
    print(
        holding.name,           # e.g. "APPLE INC"
        holding.cusip,
        holding.value,          # market value in thousands
        holding.shares,
        holding.investment_discretion,
    )
```

### Data model

```python
from pydantic import BaseModel
import datetime

class InstitutionalHolding(BaseModel):
    fund_name: str
    fund_cik: str
    period_of_report: datetime.date        # quarter end date
    company_name: str
    cusip: str
    ticker: str | None                     # resolved from CUSIP lookup
    market_value_thousands: int
    shares: int
    investment_discretion: str             # "SOLE", "SHARED", etc.
    accession_number: str

class HoldingDelta(BaseModel):
    """Quarter-over-quarter change for a single position."""
    fund_cik: str
    ticker: str
    prior_shares: int
    current_shares: int
    delta_shares: int
    action: str                            # "new", "increased", "decreased", "closed"
```

### Integration considerations

- 13F data is quarterly and stale by up to 45 days — treat it as a lagging
  indicator, not a real-time signal. Fine for idea generation, not for timing.
- CUSIP-to-ticker mapping is not included in 13F filings. `edgartools` has a
  CUSIP ticker map you can use: `edgar.get_ticker_from_cusip(cusip)`.
- Funds with >$100M AUM are required to file. Smaller funds (some of the best
  value shops) won't appear here.
- Good candidate for a scheduled weekly job (see `schedule` skill) that diffs the
  latest quarter's 13F against the prior one and writes a summary to a file or
  sends a notification.

---

## Suggested Implementation Order

1. **Form 4 first** — simpler data model, more actionable signal, lower data volume.
   A per-ticker insider feed integrates naturally alongside the existing RAG chat.
2. **13F second** — higher value for idea generation but requires a fund watchlist
   and a CUSIP resolver, so there's more setup involved.

---

## Related Future Work

See also [`PortfolioAnalysis.md`](PortfolioAnalysis.md) for the LangGraph-based
supply chain risk analyzer, which would be a natural consumer of both insider
signals and institutional holdings data as additional context nodes in the
knowledge graph.
