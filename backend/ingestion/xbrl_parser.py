"""
Extracts structured financial statements from an edgartools XBRL object and
converts them into ParsedElement objects compatible with the ingestion pipeline.

This is the STRUCTURED DATA path — it pairs with parser.py (the NARRATIVE path):

  ┌─ edgar_fetcher.get_filing_html() ──► parser.parse_filing_html()
  │    → Item sections, MD&A prose, Risk Factors, business description, etc.
  │      (narrative text chunks — the "why" behind the numbers)
  │
  └─ edgar_fetcher.get_filing_xbrl() ──► xbrl_parser.parse_xbrl_statements()
       → Income statement, balance sheet, cash flows
         (structured financial table chunks — the actual numbers)

Both paths feed into the same DocumentChunk → embed → LanceDB pipeline.
Nothing is thrown away; XBRL adds clean financial table chunks that complement
the narrative text already extracted from the HTML.
"""
import logging
from typing import Optional

from backend.ingestion.parser import ParsedElement

logger = logging.getLogger(__name__)

# Maps edgartools XBRL attribute names → friendly SEC section labels.
# These will appear as sec_item_section metadata on the resulting chunks.
_STATEMENT_CONFIG = [
    (
        "income_statement",
        "Item 8: Financial Statements - Income Statement",
    ),
    (
        "balance_sheet",
        "Item 8: Financial Statements - Balance Sheet",
    ),
    (
        "cash_flow_statement",
        "Item 8: Financial Statements - Cash Flow Statement",
    ),
]


def _dataframe_to_text(df, title: str) -> str:
    """
    Convert a financial statement DataFrame to a clean, readable text block.

    We include the title, then use pandas .to_string() which preserves column
    alignment well. The result is what the LLM summarizer (table_summarizer.py)
    will receive as input — it reads like a formatted table from an annual report.
    """
    try:
        # Drop hierarchy/structural columns that aren't meaningful for the LLM
        cols_to_drop = [c for c in ("level", "parent_concept", "parent_abstract_concept") if c in df.columns]
        display_df = df.drop(columns=cols_to_drop) if cols_to_drop else df
        table_text = display_df.to_string(index=False)
    except Exception:
        # Fallback: just use repr if something goes wrong
        table_text = str(df)

    return f"=== {title} ===\n\n{table_text}"


def _dataframe_to_csv(df) -> str:
    """
    Convert a financial statement DataFrame to CSV for raw_payload storage.
    This is what gets passed to the synthesis LLM for final answer generation
    (via the raw_payload field in DocumentChunk).
    """
    try:
        return df.to_csv(index=False)
    except Exception:
        return str(df)


def parse_xbrl_statements(xbrl_data) -> list[ParsedElement]:
    """
    Extract all available financial statements from an edgartools XBRL object
    and return them as ParsedElement instances.

    Each statement becomes one ParsedElement with:
        element_type = "table"
        content      = human-readable formatted table (sent to LLM summarizer)
        section      = e.g. "Item 8: Financial Statements - Income Statement"
        raw_html     = CSV representation of the DataFrame (stored as raw_payload)

    The caller (ingest.py) then runs these through the existing
    summarize_table() → embed → upsert path, exactly like HTML-extracted tables.

    Args:
        xbrl_data: The object returned by edgartools' filing.xbrl().

    Returns:
        List of ParsedElement objects (may be empty if XBRL data is thin).
    """
    elements: list[ParsedElement] = []

    for attr_name, section_label in _STATEMENT_CONFIG:
        stmt = getattr(xbrl_data, attr_name, None)
        if stmt is None:
            logger.warning(f"XBRL: no '{attr_name}' attribute on xbrl_data — skipping")
            continue

        try:
            df = stmt.to_dataframe()
        except Exception as e:
            logger.warning(f"XBRL: failed to call to_dataframe() on {attr_name}: {e}")
            continue

        if df is None or df.empty:
            logger.warning(f"XBRL: empty DataFrame for {attr_name} — skipping")
            continue

        title = attr_name.replace("_", " ").title()
        text_content = _dataframe_to_text(df, title)
        raw_csv = _dataframe_to_csv(df)

        element = ParsedElement(
            element_type="table",
            content=text_content,
            section=section_label,
            raw_html=raw_csv,   # raw_html field reused for CSV; becomes raw_payload in DocumentChunk
        )
        elements.append(element)
        logger.info(
            f"XBRL: extracted {attr_name} — {len(df)} rows, "
            f"{len(text_content)} chars"
        )

    logger.info(f"XBRL: extracted {len(elements)} financial statement(s)")
    return elements
