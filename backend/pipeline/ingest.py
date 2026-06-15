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
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from backend.ingestion.edgar_fetcher import (
    resolve_filing,
    html_from_filing,
    xbrl_from_filing,
)
from backend.ingestion.parser import parse_filing_html, ParsedElement
from backend.ingestion.xbrl_parser import parse_xbrl_statements
from backend.config import settings
from backend.models.schemas import DocumentChunk
from backend.pipeline.ratelimit import TokenBucket
from backend.pipeline.table_summarizer import summarize_tables
from backend.pipeline.embedder import embed_texts
from backend.pipeline.store import upsert_chunks, generate_chunk_id

logger = logging.getLogger(__name__)

# Progress callback: receives a dict like {"stage": "fetching", ...}. Optional;
# the API layer wires this to per-task status so the UI can show live stages.
ProgressCallback = Callable[[dict], None]

# Target size for merged text chunks (~1 filing page)
_TEXT_CHUNK_TARGET = 2500
# Characters carried over from the end of one text chunk into the next within
# the same section, so a fact spanning a size-based boundary appears whole in
# at least one chunk.
_TEXT_CHUNK_OVERLAP = 250
# Minimum characters for any chunk to be worth embedding
_MIN_CHUNK_LENGTH = 200

# ── Table-summarization parallelism / rate limiting ──────────────────────────
# Requests-per-minute budget for the table-summary LLM, the max number of
# concurrent in-flight summary calls, and how many tables share one LLM call.
# Defaults come from config (free-tier-tuned) but stay module-level so tests can
# monkeypatch them. A token bucket (ratelimit.TokenBucket) enforces _TABLE_RPM
# across worker threads; batching is what actually beats the RPM ceiling.
_TABLE_RPM = settings.table_summary_rpm
_TABLE_MAX_CONCURRENCY = settings.table_summary_concurrency
_TABLE_BATCH_SIZE = settings.table_summary_batch_size


def _tail_overlap(text: str, size: int = _TEXT_CHUNK_OVERLAP) -> str:
    """Last ~``size`` characters of ``text``, trimmed to a word boundary."""
    if len(text) <= size:
        return text
    tail = text[-size:]
    # Drop the (likely partial) first word so the overlap starts cleanly.
    cut = tail.find(" ")
    if cut != -1:
        tail = tail[cut + 1:]
    return tail


def _merge_text_elements(elements: list[ParsedElement]) -> list[ParsedElement]:
    """
    Merge consecutive text elements from the same section into page-sized chunks.
    Tables are left as individual elements — they get their own summarization pass.

    When a chunk is split because it reached the size target (NOT on a section
    change), the tail of the previous chunk is carried into the next one as a
    sliding-window overlap, so facts spanning the boundary survive in full in
    at least one chunk.
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
            if buffer_section and el.section != buffer_section:
                # Section boundary: hard break, no overlap across sections.
                flush()
            elif buffer_section and len(buffer_text) >= _TEXT_CHUNK_TARGET:
                # Size boundary within a section: flush, then seed the next
                # chunk with the tail of this one (sliding-window overlap).
                overlap = _tail_overlap(buffer_text)
                section = buffer_section
                flush()
                buffer_text = overlap
                buffer_section = section
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
    # Keep elements that clear the minimum length, preserving their ORIGINAL
    # positional index `i` (used for chunk_id) so ordering and the
    # index→chunk mapping stay byte-for-byte identical to the serial version.
    kept: list[tuple[int, ParsedElement]] = [
        (i, el) for i, el in enumerate(elements) if len(el.content) >= _MIN_CHUNK_LENGTH
    ]

    # Pre-clean table HTML up front (cheap, deterministic) so the parallel pass
    # only does the network-bound LLM call.
    table_indices = [pos for pos, (_, el) in enumerate(kept) if el.element_type == "table"]
    cleaned_html: dict[int, str] = {
        pos: _clean_table_html(kept[pos][1].raw_html or kept[pos][1].content)
        for pos in table_indices
    }

    # Table-summarization pass: tables are grouped into BATCHES, each summarized
    # in a single LLM call, and the batches run in parallel under a thread-safe
    # token bucket. Batching is the real throughput lever — on a rate-limited
    # (e.g. free-tier) provider, collapsing N calls into N/batch_size calls beats
    # raw concurrency, which the RPM ceiling caps anyway. The token bucket spends
    # ONE token per batch. Results are reassembled in original element order.
    summaries: dict[int, str] = {}
    if table_indices:
        bucket = TokenBucket(rate_per_sec=_TABLE_RPM / 60.0, capacity=_TABLE_MAX_CONCURRENCY)
        batch_size = max(1, _TABLE_BATCH_SIZE)
        batches = [
            table_indices[i : i + batch_size]
            for i in range(0, len(table_indices), batch_size)
        ]

        def _summarize_batch(batch: list[int]) -> dict[int, str]:
            raw_htmls = [cleaned_html[pos] for pos in batch]
            try:
                bucket.acquire()  # one token per BATCH — throttles to _TABLE_RPM
                results = summarize_tables(
                    tables=raw_htmls,
                    ticker=ticker,
                    document_type=document_type,
                )
            except Exception as e:
                logger.warning(f"Table summarization failed (using raw text fallback): {e}")
                results = [None] * len(batch)
            # Empty/failed summary → fall back to the element's raw content.
            return {
                pos: (summary or kept[pos][1].content)
                for pos, summary in zip(batch, results)
            }

        workers = min(_TABLE_MAX_CONCURRENCY, len(batches))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for partial in executor.map(_summarize_batch, batches):
                summaries.update(partial)

    # Reassemble in original element order.
    chunks: list[DocumentChunk] = []
    texts_to_embed: list[str] = []
    for pos, (i, element) in enumerate(kept):
        if element.element_type == "table":
            text_content = summaries[pos]
            raw_payload = cleaned_html[pos]
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


def _path_a_html(filing, ticker: str, document_type: str, year: Optional[int]) -> list[ParsedElement]:
    """PATH A — narrative text from the filing's primary HTML document.

    Fetches the HTML and partitions it into section-tagged elements
    (NarrativeText, Table, Title). Keeps ALL element types (text AND tables)
    as a fallback for financial data not captured in XBRL (non-standard tables,
    segment breakdowns). A failure here is fatal to the ingest — narrative is
    the backbone of RAG quality.
    """
    logger.info(f"[PATH A] Fetching HTML for {ticker} {document_type} (year={year})")
    html_content = html_from_filing(filing)
    html_doc = parse_filing_html(html_content)
    logger.info(f"[PATH A] {len(html_doc.elements)} elements from HTML")
    return html_doc.elements


def _path_b_xbrl(filing, ticker: str, document_type: str, year: Optional[int]) -> list[ParsedElement]:
    """PATH B — structured financials from XBRL.

    Extracts the three core statements as clean DataFrames. Non-fatal: returns
    an empty list (never raises) if XBRL is unavailable (older filings, foreign
    issuers) or errors, so the narrative path still completes the ingest.
    """
    try:
        logger.info(f"[PATH B] Fetching XBRL for {ticker} {document_type} (year={year})")
        xbrl_data = xbrl_from_filing(filing)
        xbrl_elements = parse_xbrl_statements(xbrl_data)
        logger.info(f"[PATH B] {len(xbrl_elements)} financial statement(s) from XBRL")
        return xbrl_elements
    except RuntimeError as e:
        # filing.xbrl() returned None — no XBRL available for this filing
        logger.warning(f"[PATH B] XBRL unavailable, skipping structured financials: {e}")
    except Exception as e:
        # Network error, parsing error, etc. — don't fail the whole ingest
        logger.error(f"[PATH B] Unexpected XBRL error, skipping: {e}", exc_info=True)
    return []


def ingest_filing(
    ticker: str,
    document_type: str = "10-K",
    year: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> int:
    """
    Full two-path pipeline: fetch → parse → summarize tables → embed → store.
    Returns the number of chunks written to LanceDB.

    ``on_progress`` (optional) is invoked with a ``{"stage": ..., ...}`` dict at
    each pipeline phase so callers (the API) can surface live status to the UI.
    It must never raise; any callback exception is swallowed.
    """
    def emit(stage: str, **detail) -> None:
        if on_progress is None:
            return
        try:
            on_progress({"stage": stage, **detail})
        except Exception:  # pragma: no cover — progress must never break ingest
            logger.debug("progress callback raised; ignoring", exc_info=True)

    # ── Resolve the filing ONCE ──────────────────────────────────────────────
    # Both PATH A (HTML) and PATH B (XBRL) operate on the SAME filing. Resolving
    # the company + filing list a single time here avoids a double EDGAR round
    # trip, and lets both paths share one filing object.
    logger.info(f"Resolving {document_type} filing for {ticker} (year={year})")
    emit("resolving", ticker=ticker, document_type=document_type, year=year)
    filing, meta = resolve_filing(ticker, document_type, year)

    # ── PATH A and PATH B run CONCURRENTLY ───────────────────────────────────
    # Both are independent, network-bound (EDGAR fetch) + CPU-bound (parse)
    # given the shared resolved filing. Running them in parallel overlaps the
    # two fetches instead of paying for them back-to-back. PATH A is fatal on
    # error; PATH B is best-effort (returns [] on failure).
    emit("fetching", filing_date=meta.get("filing_date"))
    all_elements: list[ParsedElement] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_path_a_html, filing, ticker, document_type, year)
        fut_b = pool.submit(_path_b_xbrl, filing, ticker, document_type, year)
        html_elements = fut_a.result()           # propagates PATH A failures
        xbrl_elements = fut_b.result()           # already swallowed internally
    all_elements.extend(html_elements)
    all_elements.extend(xbrl_elements)
    emit("parsing", html_elements=len(html_elements), xbrl_elements=len(xbrl_elements))

    # ── Merge text elements into page-sized chunks ────────────────────────────
    all_elements = _merge_text_elements(all_elements)
    logger.info(f"Processing {len(all_elements)} merged elements for {ticker}")
    n_tables = sum(1 for el in all_elements if el.element_type == "table")
    emit("summarizing_tables", elements=len(all_elements), tables=n_tables)
    chunks, texts_to_embed = _elements_to_chunks(
        elements=all_elements,
        meta=meta,
        document_type=document_type,
        ticker=ticker,
    )

    if not chunks:
        logger.warning(f"No usable chunks found for {ticker} {document_type} {year}")
        emit("done", chunks=0)
        return 0

    # ── Embed + store ─────────────────────────────────────────────────────────
    logger.info(f"Embedding {len(chunks)} chunks for {ticker}")
    emit("embedding", chunks=len(chunks))
    vectors = embed_texts(texts_to_embed)

    emit("storing", chunks=len(chunks))
    written = upsert_chunks(chunks, vectors)
    logger.info(f"Ingestion complete: {written} chunks stored for {ticker}")
    emit("done", chunks=written)
    return written
