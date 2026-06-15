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


# Currency symbols that SEC filings place in their own cell before a value.
_CURRENCY_SYMBOLS = ("$", "€", "£", "¥")
# A cell is "numeric" (i.e. a data cell, not a header) if it contains a run of
# at least 2 consecutive digits.
_NUMERIC_RE = re.compile(r"\d{2,}")


def _cell_text(cell) -> str:
    """Visible text of a <td>/<th>, tags stripped and whitespace-collapsed."""
    return cell.get_text(strip=True)


def _clean_table_html(html: str) -> str:
    """
    Clean up SEC filing HTML tables using an HTML parser (BeautifulSoup + lxml)
    rather than regex, so it stays correct on nested tables, <th> headers,
    colspans and other real-world filing markup:

    - Merge a lone currency-symbol cell ($/€/£/¥) into the following number cell
    - Merge a trailing "%" cell into the preceding cell
    - Standardize self-closing/empty cells
    - Drop rows that are entirely empty (no text in any cell)
    - Wrap leading non-numeric rows in <thead>, data rows in <tbody>

    Operates on the OUTERMOST table only; nested tables are left untouched so
    they are not corrupted. On any parse failure the input is returned
    unchanged (logged as a warning). Empty/whitespace input is returned as-is.

    Signature is load-bearing: this is called from ``_elements_to_chunks`` and
    monkeypatched in tests, so the name + ``(html: str) -> str`` shape must stay.
    """
    if not html or not html.strip():
        return html

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if table is None:
            return html

        # Process only the rows that belong directly to THIS (outermost) table,
        # never rows that live inside a nested table — those keep their own
        # markup intact.
        def _owning_table(node):
            return node.find_parent("table")

        rows = [r for r in table.find_all("tr") if _owning_table(r) is table]

        for row in rows:
            cells = [c for c in row.find_all(["td", "th"]) if _owning_table(c) is table]
            _merge_currency_cells(cells)
            _merge_percent_cells(cells)

        # Drop fully-empty rows (after merging) that belong to this table.
        for row in list(rows):
            row_cells = [c for c in row.find_all(["td", "th"]) if _owning_table(c) is table]
            if row_cells and not any(_cell_text(c) for c in row_cells):
                row.decompose()

        _wrap_thead(soup, table)

        return str(table)
    except Exception:  # pragma: no cover - defensive: never break ingest
        logger.warning("table HTML cleanup failed; returning input unchanged", exc_info=True)
        return html


def _merge_currency_cells(cells: list) -> None:
    """Merge each lone currency-symbol cell into the following sibling cell.

    ``<td>$</td><td>123</td>`` becomes ``<td>$123</td>`` (the symbol cell is
    removed). The merged value carries the *following* cell's attributes,
    matching the prior regex behavior.
    """
    for cell in list(cells):
        text = _cell_text(cell)
        if text not in _CURRENCY_SYMBOLS:
            continue
        nxt = cell.find_next_sibling(["td", "th"])
        if nxt is None:
            continue
        nxt.string = f"{text}{_cell_text(nxt)}"
        cell.decompose()
        cells.remove(cell)


def _merge_percent_cells(cells: list) -> None:
    """Merge a trailing lone ``%`` cell into the preceding sibling cell.

    ``<td>23</td><td>%</td>`` becomes ``<td>23%</td>`` (the percent cell is
    removed). The merged value keeps the *preceding* cell's attributes.
    """
    for cell in list(cells):
        if _cell_text(cell) != "%":
            continue
        prev = cell.find_previous_sibling(["td", "th"])
        if prev is None:
            continue
        prev.string = f"{_cell_text(prev)}%"
        cell.decompose()
        if cell in cells:
            cells.remove(cell)


def _wrap_thead(soup, table) -> None:
    """
    Detect leading header rows (no numeric-looking cell) and wrap them in
    <thead>, with the remaining rows in <tbody>. A cell is numeric when it
    contains 2+ consecutive digits. Operates on the outermost table's own rows
    only; nested tables are left alone. Existing <thead>/<tbody>/<tr> nesting is
    rebuilt from scratch so the output is normalized.
    """
    def _owning_table(node):
        return node.find_parent("table")

    rows = [r for r in table.find_all("tr") if _owning_table(r) is table]
    if not rows:
        return

    header_rows, data_rows = [], []
    past_header = False
    for row in rows:
        cells = [c for c in row.find_all(["td", "th"]) if _owning_table(c) is table]
        has_numbers = any(_NUMERIC_RE.search(_cell_text(c)) for c in cells if _cell_text(c))
        if not past_header and not has_numbers:
            header_rows.append(row)
        else:
            past_header = True
            data_rows.append(row)

    # Detach every row, then re-attach under fresh <thead>/<tbody> wrappers.
    for row in rows:
        row.extract()

    # Clear out any pre-existing section wrappers (thead/tbody/tfoot) that
    # belonged to this table so we don't leave empty shells behind.
    for section in table.find_all(["thead", "tbody", "tfoot"]):
        if _owning_table(section) is table:
            section.decompose()

    if header_rows:
        thead = soup.new_tag("thead")
        for row in header_rows:
            thead.append(row)
        table.append(thead)
    if data_rows:
        tbody = soup.new_tag("tbody")
        for row in data_rows:
            tbody.append(row)
        table.append(tbody)


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
            period_of_report=meta.get("period_of_report"),
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
