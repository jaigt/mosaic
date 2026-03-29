"""
Orchestrates the full ingestion pipeline for a single SEC filing via two
complementary paths that together capture everything in the document:

  PATH A — Narrative (HTML → unstructured):
    Extracts prose sections: MD&A, Risk Factors, Business description, etc.
    These are the "why behind the numbers" — critical for RAG quality.

  PATH B — Structured financials (XBRL → edgartools):
    Extracts the income statement, balance sheet, and cash flow statement as
    clean, structured DataFrames. Far more reliable than pulling tables from
    raw HTML, especially for multi-year comparison columns and footnotes.

Both paths produce DocumentChunk objects that go through the same
summarize → embed → upsert pipeline. Nothing is discarded.
"""
import logging
import re
import time
from typing import Optional

from backend.ingestion.edgar_fetcher import get_filing_html, get_filing_xbrl
from backend.ingestion.parser import parse_filing_html, ParsedElement
from backend.ingestion.xbrl_parser import parse_xbrl_statements
from backend.models.schemas import DocumentChunk
from backend.pipeline.table_summarizer import summarize_table
from backend.pipeline.embedder import embed_texts
from backend.pipeline.store import upsert_chunks, generate_chunk_id

logger = logging.getLogger(__name__)

# Target size for merged text chunks (~1 filing page)
_TEXT_CHUNK_TARGET = 2500
# Minimum characters for any chunk to be worth embedding
_MIN_CHUNK_LENGTH = 200


def _merge_text_elements(elements: list[ParsedElement]) -> list[ParsedElement]:
    """
    Merge consecutive text elements from the same section into page-sized chunks.
    Tables are left as individual elements — they get their own summarization pass.
    """
    merged: list[ParsedElement] = []
    buffer_text = ""
    buffer_section = ""

    def flush():
        nonlocal buffer_text, buffer_section
        if buffer_text.strip():
            merged.append(ParsedElement(
                element_type="text",
                content=buffer_text.strip(),
                section=buffer_section,
            ))
        buffer_text = ""
        buffer_section = ""

    for el in elements:
        if el.element_type == "table":
            flush()
            merged.append(el)
        else:
            # Start a new buffer on section change or when target size reached
            if buffer_section and (el.section != buffer_section or len(buffer_text) >= _TEXT_CHUNK_TARGET):
                flush()
            buffer_section = el.section
            buffer_text += ("\n\n" if buffer_text else "") + el.content

    flush()
    return merged


def _clean_table_html(html: str) -> str:
    """
    Clean up SEC filing HTML tables:
    - Merge currency symbol cells ($ €) into the following number cell
    - Remove self-closing empty cells (standardize to <td></td>)
    - Remove rows that become entirely empty after cleaning
    - Wrap leading non-numeric rows in <thead>
    """
    # Merge: <td>$</td><td>123</td>  →  <td>$123</td>
    # SEC filings put $ in its own cell before the value
    html = re.sub(
        r'<td[^>]*>\s*(\$|€|£|¥)\s*</td>\s*<td([^>]*)>(.*?)</td>',
        lambda m: f'<td{m.group(2)}>{m.group(1)}{m.group(3).strip()}</td>',
        html,
        flags=re.DOTALL,
    )
    # Merge: <td>23</td><td>%</td>  →  <td>23%</td>
    html = re.sub(
        r'<td([^>]*)>(.*?)</td>\s*<td[^>]*>\s*%\s*</td>',
        lambda m: f'<td{m.group(1)}>{m.group(2).strip()}%</td>',
        html,
        flags=re.DOTALL,
    )
    # Standardize self-closing empty cells to <td></td> (helps some browsers)
    html = re.sub(r'<td\s*/>', '<td></td>', html)
    
    # DO NOT remove <td></td> cells here — they are often padding for column alignment!
    
    # Remove rows that are entirely empty (no text at all in any cell)
    def is_row_empty(row_html: str) -> bool:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        # Strip tags and whitespace from each cell to see if anything is left
        return not any(re.sub(r'<[^>]+>', '', c).strip() for c in cells)

    rows = re.findall(r'(<tr[^>]*>.*?</tr>)', html, re.DOTALL)
    cleaned_rows = [r for r in rows if not is_row_empty(r)]
    
    # Rebuild table with cleaned rows
    table_match = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if table_match:
        html = f'<table>{"".join(cleaned_rows)}</table>'
    
    # Wrap leading non-numeric rows in <thead> so CSS can center them
    html = _add_thead(html)
    return html


def _add_thead(html: str) -> str:
    """
    Detect header rows (rows with no numeric-looking cells) at the top of a table
    and wrap them in <thead> so they can be styled separately from data rows.
    """
    _NUMERIC_RE = re.compile(r'\d{2,}')  # at least 2 digits = likely a data cell

    def upgrade_table(m: re.Match) -> str:
        body = m.group(1)
        rows = re.findall(r'(<tr[^>]*>.*?</tr>)', body, re.DOTALL)
        if not rows:
            return m.group(0)

        header_rows, data_rows = [], []
        past_header = False
        for row in rows:
            cell_texts = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            cell_texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cell_texts]
            has_numbers = any(_NUMERIC_RE.search(c) for c in cell_texts if c)
            if not past_header and not has_numbers:
                header_rows.append(row)
            else:
                past_header = True
                data_rows.append(row)

        result = ''
        if header_rows:
            result += '<thead>' + ''.join(header_rows) + '</thead>'
        if data_rows:
            result += '<tbody>' + ''.join(data_rows) + '</tbody>'
        return f'<table>{result}</table>'

    return re.sub(r'<table[^>]*>(.*?)</table>', upgrade_table, html, flags=re.DOTALL)


def _elements_to_chunks(
    elements: list[ParsedElement],
    meta: dict,
    document_type: str,
    ticker: str,
    index_offset: int = 0,
) -> tuple[list[DocumentChunk], list[str]]:
    """
    Convert a list of ParsedElement objects into DocumentChunk + embed-text pairs.
    Applies the two-pass table strategy: tables go through the LLM summarizer,
    text elements are embedded directly.

    Args:
        index_offset: Offset added to element index for chunk_id uniqueness
                      (prevents collisions when merging HTML and XBRL elements).
    """
    chunks: list[DocumentChunk] = []
    texts_to_embed: list[str] = []

    for i, element in enumerate(elements):
        if len(element.content) < _MIN_CHUNK_LENGTH:
            continue

        if element.element_type == "table":
            # Two-pass strategy: LLM converts raw table → semantic summary for embedding.
            # Falls back to raw table text if the LLM call fails (rate limit, quota, etc.)
            raw_html = _clean_table_html(element.raw_html or element.content)
            try:
                time.sleep(0.5)  # Respect free-tier rate limits (2 RPM safety margin)
                text_content = summarize_table(
                    table_content=raw_html,
                    ticker=ticker,
                    document_type=document_type,
                )
                if not text_content:
                    text_content = element.content
            except Exception as e:
                logger.warning(f"Table summarization failed (using raw text fallback): {e}")
                text_content = element.content
            raw_payload = raw_html
            chunk_type = "table"
        else:
            # Narrative text: embed as-is
            text_content = element.content
            raw_payload = element.content
            chunk_type = "text"

        chunk = DocumentChunk(
            chunk_id=generate_chunk_id(
                ticker=meta["ticker"],
                doc_type=document_type,
                year=meta["filing_year"],
                quarter=meta["filing_quarter"],
                index=index_offset + i,
            ),
            ticker=meta["ticker"],
            cik=meta["cik"],
            document_type=document_type,
            filing_year=meta["filing_year"],
            filing_quarter=meta["filing_quarter"],
            sec_item_section=element.section,
            chunk_type=chunk_type,
            text_content=text_content,
            raw_payload=raw_payload,
        )
        chunks.append(chunk)
        texts_to_embed.append(text_content)

    return chunks, texts_to_embed


def ingest_filing(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
) -> int:
    """
    Full two-path pipeline: fetch → parse → summarize tables → embed → store.
    Returns the number of chunks written to LanceDB.
    """
    all_elements: list[ParsedElement] = []

    # ── PATH A: Narrative text from HTML ─────────────────────────────────────
    # Fetches the primary HTML document and partitions it into section-tagged
    # elements (NarrativeText, Table, Title).  We keep ALL element types here
    # (text AND tables from HTML) as a fallback for any financial data that
    # isn't captured in XBRL (e.g., non-standard tables, segment breakdowns).
    logger.info(f"[PATH A] Fetching HTML for {ticker} {document_type} (year={year})")
    html_content, meta = get_filing_html(ticker, document_type, year)
    html_doc = parse_filing_html(html_content)
    all_elements.extend(html_doc.elements)
    logger.info(f"[PATH A] {len(html_doc.elements)} elements from HTML")

    # ── PATH B: Structured financials from XBRL ───────────────────────────────
    # Fetches the XBRL instance document and extracts the three core financial
    # statements as clean DataFrames.  These replace the noisy HTML-extracted
    # versions of the same tables with accurate, properly labelled data.
    # Gracefully skipped if XBRL is unavailable (older filings, foreign issuers).
    try:
        logger.info(f"[PATH B] Fetching XBRL for {ticker} {document_type} (year={year})")
        xbrl_data, _xbrl_meta = get_filing_xbrl(ticker, document_type, year)
        xbrl_elements = parse_xbrl_statements(xbrl_data)
        all_elements.extend(xbrl_elements)
        logger.info(f"[PATH B] {len(xbrl_elements)} financial statement(s) from XBRL")
    except RuntimeError as e:
        # filing.xbrl() returned None — no XBRL available for this filing
        logger.warning(f"[PATH B] XBRL unavailable, skipping structured financials: {e}")
    except Exception as e:
        # Network error, parsing error, etc. — don't fail the whole ingest
        logger.error(f"[PATH B] Unexpected XBRL error, skipping: {e}", exc_info=True)

    # ── Merge text elements into page-sized chunks ────────────────────────────
    all_elements = _merge_text_elements(all_elements)
    logger.info(f"Processing {len(all_elements)} merged elements for {ticker}")
    chunks, texts_to_embed = _elements_to_chunks(
        elements=all_elements,
        meta=meta,
        document_type=document_type,
        ticker=ticker,
    )

    if not chunks:
        logger.warning(f"No usable chunks found for {ticker} {document_type} {year}")
        return 0

    # ── Embed + store ─────────────────────────────────────────────────────────
    logger.info(f"Embedding {len(chunks)} chunks for {ticker}")
    vectors = embed_texts(texts_to_embed)

    written = upsert_chunks(chunks, vectors)
    logger.info(f"Ingestion complete: {written} chunks stored for {ticker}")
    return written
