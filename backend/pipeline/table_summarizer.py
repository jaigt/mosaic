"""
Two-pass table strategy: sends raw SEC tables to the fast LLM (Gemini Flash)
to generate semantic summaries suitable for embedding.
POC Decision: Using gemini-2.0-flash on AI Studio free tier.
"""
import logging
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import settings
from backend.pipeline.llm import generate

logger = logging.getLogger(__name__)

_TABLE_SUMMARY_PROMPT = """\
You are a financial analyst reviewing an SEC filing. Summarize the following \
financial table extracted from a {document_type} filing for {ticker}.

State:
1. What the table measures (e.g., revenue, operating expenses, debt)
2. Key metrics and their values for the most recent period
3. Notable year-over-year changes or trends
4. Any red flags or standout figures

Output ONLY the summary. No preamble, no markdown headers.

TABLE:
{table_content}
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def summarize_table(
    table_content: str,
    ticker: str,
    document_type: str,
) -> str:
    """
    Send a raw table to Gemini Flash and return a semantic summary.
    Retries up to 3 times on failure with exponential backoff.
    """
    if not table_content.strip():
        return ""

    prompt = _TABLE_SUMMARY_PROMPT.format(
        document_type=document_type,
        ticker=ticker,
        table_content=table_content[:8000],  # Trim to avoid token overflow on large tables
    )

    summary = generate(prompt, model=settings.fast_model).strip()
    logger.debug(f"Table summary ({len(summary)} chars) for {ticker}")
    return summary


# Sentinel the batch model is told to place between consecutive summaries. Made
# deliberately unlikely to occur in a financial-table summary.
_BATCH_DELIM = "<<<§TABLE_BREAK§>>>"

_BATCH_SUMMARY_PROMPT = """\
You are a financial analyst reviewing an SEC {document_type} filing for {ticker}.
Below are {n} financial tables, each introduced by a line "### TABLE k".

For EACH table, write a summary stating:
1. What the table measures (e.g., revenue, operating expenses, debt)
2. Key metrics and their values for the most recent period
3. Notable year-over-year changes or trends
4. Any red flags or standout figures

Output the {n} summaries IN THE SAME ORDER, separated by a line containing
exactly "{delim}" and nothing else. Produce exactly {n} summaries — one per
table, even if a table looks empty (write "No usable data." in that case).
No preamble, no markdown headers, no table numbers in the output.

{body}
"""


# Retry transient (network/provider) failures, but NOT a ValueError: a count
# mismatch is deterministic, so retrying the same prompt would only waste calls.
# It fails fast to the per-table fallback instead.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(ValueError),
)
def _summarize_batch_call(tables: list[str], ticker: str, document_type: str) -> list[str]:
    """One LLM call summarizing several tables; returns one summary per table.

    Raises ValueError if the model does not return exactly ``len(tables)``
    delimited summaries, so the caller can fall back to per-table calls.
    """
    # Trim each table harder than the single-call path since several share one
    # request's token budget.
    per_table_limit = max(1500, 8000 // max(len(tables), 1))
    body = "\n\n".join(
        f"### TABLE {i + 1}\n{t[:per_table_limit]}" for i, t in enumerate(tables)
    )
    prompt = _BATCH_SUMMARY_PROMPT.format(
        document_type=document_type,
        ticker=ticker,
        n=len(tables),
        delim=_BATCH_DELIM,
        body=body,
    )
    raw = generate(prompt, model=settings.fast_model)
    parts = [p.strip() for p in raw.split(_BATCH_DELIM)]
    if len(parts) != len(tables):
        raise ValueError(
            f"batch summary returned {len(parts)} parts for {len(tables)} tables"
        )
    return parts


def summarize_tables(
    tables: list[str],
    ticker: str,
    document_type: str,
) -> list[str]:
    """Summarize a batch of tables in a SINGLE LLM call where possible.

    Returns one summary per input table, in order. This is the throughput lever
    for ingestion: collapsing N rate-limited calls into one. If the batched call
    fails or returns a mismatched count, falls back to per-table calls so the
    result is always correct (just slower for that batch).
    """
    if not tables:
        return []
    if len(tables) == 1:
        return [summarize_table(tables[0], ticker, document_type)]
    try:
        return _summarize_batch_call(tables, ticker, document_type)
    except Exception as e:  # noqa: BLE001 — fall back to the reliable path
        logger.warning(
            f"Batched table summary failed ({e}); falling back to per-table calls"
        )
        return [summarize_table(t, ticker, document_type) for t in tables]
