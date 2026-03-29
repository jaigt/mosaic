"""
Phase 4: Extracts structured metadata filters from a natural language query
using the fast LLM, so LanceDB pre-filtering is applied before vector search.
"""
import json
import logging
import re
from typing import Optional

from backend.config import settings
from backend.pipeline.llm import generate

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Extract structured metadata filters from the following financial query.
Return ONLY a JSON object with these optional fields:
- "ticker": stock ticker symbol (string, uppercase), if mentioned
- "year": filing year as integer, if mentioned
- "document_type": one of "10-K", "10-Q", "8-K", if mentioned
- "section": SEC section name if mentioned (e.g., "Item 7", "MD&A", "Risk Factors")

If a field is not clearly mentioned, omit it from the JSON.
Do not include any explanation, only the JSON object.

Query: {query}
"""


def extract_filters(query: str) -> dict:
    """
    Returns a dict with any of: ticker, year, document_type, section.
    Falls back to empty dict if parsing fails.
    """
    prompt = _EXTRACTION_PROMPT.format(query=query)
    try:
        response_text = generate(prompt, model=settings.fast_model)
        raw = response_text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        filters = json.loads(raw)
        logger.debug(f"Extracted filters: {filters}")
        return filters
    except Exception as e:
        logger.warning(f"Filter extraction failed, proceeding without filters: {e}")
        return {}
