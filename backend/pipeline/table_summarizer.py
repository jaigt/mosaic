"""
Two-pass table strategy: sends raw SEC tables to the fast LLM (Gemini Flash)
to generate semantic summaries suitable for embedding.
POC Decision: Using gemini-2.0-flash on AI Studio free tier.
"""
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

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
