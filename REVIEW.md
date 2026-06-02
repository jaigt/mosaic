# Repository Review

Date: 2026-04-29
Reviewer: Codex
Scope: Static code review of backend + frontend implementation.

## Findings (Ordered by severity)

### 1) High - Incorrect 10-Q quarter inference can mislabel filings
- Issue: Quarter buckets overlap and first-match wins (`4` is in both Q1/Q2, `7` is in both Q2/Q3), so some 10-Q filings can be assigned the wrong quarter.
- Impact: Incorrect metadata labels degrade retrieval filtering and can produce misleading responses/citations.
- Evidence: `backend/ingestion/edgar_fetcher.py:121`
- Recommendation: Replace month-based heuristic with period-end / report-period metadata from filing/XBRL when available. If heuristic is required, use non-overlapping ranges and unit tests for boundary months.

### 2) High - Potential injection risk in LanceDB filter construction
- Issue: User/LLM-derived strings are interpolated directly into `where(...)` clauses.
- Impact: Malformed values containing quotes can break queries; depending on backend parser behavior, this may create injection-like behavior.
- Evidence: `backend/retrieval/retriever.py:37`
- Recommendation: Sanitize/escape filter inputs or use a parameterized query path if supported. Strictly validate ticker/doc type against allowlists before interpolation.

### 3) High - Unsanitized HTML rendering in source viewer (`dangerouslySetInnerHTML`)
- Issue: Source payload is injected as HTML without sanitization.
- Impact: XSS risk if upstream payload is untrusted or unexpectedly contains executable content.
- Evidence: `frontend/src/components/SourcePanel.tsx:136`
- Recommendation: Sanitize with a robust HTML sanitizer (for example DOMPurify) and apply a strict allowed-tags/attributes policy.

### 4) Medium - XBRL extraction path appears incompatible with current edgartools API
- Issue: Parser expects statement attributes that may not exist in current objects.
- Impact: Structured financial statement ingestion silently degrades; quality relies mostly on HTML path.
- Evidence: `backend/ingestion/xbrl_parser.py:98`
- Recommendation: Update parser to current edgartools interfaces and add a regression test using a known filing fixture.

### 5) Medium - Ingest modal blocks current year entries
- Issue: Year input hardcoded with `max="2025"`.
- Impact: On 2026-04-29, users cannot enter year 2026 in UI.
- Evidence: `frontend/src/components/IngestModal.tsx:123`
- Recommendation: Use dynamic max year (`new Date().getFullYear()`) or remove max constraint and validate server-side.

### 6) Medium - `/filings` endpoint masks backend failures
- Issue: Broad exception handling returns `{ filings: [] }` on any error.
- Impact: Operational failures appear as "no data," making debugging and observability poor.
- Evidence: `backend/api/main.py:142`
- Recommendation: Log structured error details and return a non-2xx status for real failures.

### 7) Low - `conversation_history` is accepted but not used
- Issue: Frontend sends conversation history, backend schema accepts it, synthesis prompt does not include it.
- Impact: Multi-turn behavior may not match user expectations.
- Evidence: `backend/models/schemas.py`, `backend/api/main.py:185`, `frontend/src/components/ChatPanel.tsx:37`
- Recommendation: Either incorporate bounded history into prompt construction or remove the field to avoid misleading API shape.

## Additional improvement opportunities
- Add tests for quarter inference edge months and retrieval filter construction.
- Add security-focused tests/checks for HTML rendering path.
- Strengthen ingest task status model (typed states + metadata) instead of string prefixes.
- Improve `/filings` implementation efficiency by avoiding repeated full `to_pandas()` calls.

## Review limitations
- This was a static review; end-to-end runtime validation was not executed in this pass.
