"""Pure decision logic + a thin verification wrapper for the analyst agent.

Keeping the *decisions* pure (no network, no LLM) makes the agent's behaviour
deterministic and unit-testable; only ``verify_answer`` touches an LLM, and that
call is injectable and degrades gracefully.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ingest_filing / IngestRequest only support these forms; anything else (e.g. an
# 8-K the user asked about) is clamped to the annual report for auto-ingest.
_INGESTABLE_DOC_TYPES = {"10-K", "10-Q"}


@dataclass
class IngestPlan:
    """An auto-ingest the agent decided to perform before answering."""

    ticker: str
    document_type: str = "10-K"
    year: Optional[int] = None

    @property
    def label(self) -> str:
        span = f" ({self.year})" if self.year else " (latest)"
        return f"{self.ticker} {self.document_type}{span}"


def plan_auto_ingest(
    requested_ticker: Optional[str],
    requested_doc_type: Optional[str],
    requested_year: Optional[int],
    retrieved_chunks: list,
) -> Optional[IngestPlan]:
    """Decide whether to fetch a missing filing before answering. PURE.

    Returns an :class:`IngestPlan` when the user clearly asked about a specific
    ticker that the retrieval did NOT surface (corpus lacks it, or a filter
    excluded everything), and ``None`` otherwise. We never guess a ticker the
    user didn't name — auto-ingest is for "you don't have NVDA yet", not for
    speculative fetching.

    The decision uses only the retrieved chunks (no extra table scan): if none
    of the returned chunks are for the requested ticker, the corpus is missing
    it for this query.
    """
    if not requested_ticker:
        return None
    ticker = requested_ticker.strip().upper()
    if not ticker:
        return None

    retrieved_tickers = {
        getattr(c.chunk, "ticker", "").upper()
        for c in retrieved_chunks
        if getattr(c, "chunk", None) is not None
    }
    if ticker in retrieved_tickers:
        return None  # we already have material for this ticker

    doc_type = (requested_doc_type or "10-K").upper()
    if doc_type not in _INGESTABLE_DOC_TYPES:
        doc_type = "10-K"
    return IngestPlan(ticker=ticker, document_type=doc_type, year=requested_year)


# ── Self-verification ────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """Outcome of the critic pass over a synthesized answer."""

    status: str = "unknown"          # "supported" | "caveats" | "unknown"
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "issues": self.issues}


_VERIFICATION_PROMPT = """\
You are a careful fact-checker auditing a financial analyst's answer against SEC \
filing excerpts. Catch claims that MATERIALLY CONTRADICT the SOURCES or are \
clearly fabricated — do NOT nitpick formatting.

Return ONLY a JSON object:
{{"supported": true|false, "issues": ["short description of each genuinely \
unsupported or contradicted claim"]}}

Treat these as SUPPORTED — do NOT flag them:
- Unit conversions and rounding: "$209,586 million", "$209.6 billion", and \
"$209.6B" are the SAME figure; "$416.16B" matches "$416,161 million".
- Percentages, sums, differences, growth rates, or ratios correctly derived from \
figures in the sources.
- Rephrasing, summarizing, reordering, rounding, or citation-number/formatting \
differences.
- Reasonable, well-known general context.

Flag a claim ONLY when:
- A specific number directly CONTRADICTS the sources (a different value for the \
same line item), OR
- A specific, material figure or named fact in the ANSWER has no basis anywhere \
in the SOURCES.

The SOURCES may be a PARTIAL excerpt, so never flag a claim merely because you \
don't see its source here — flag only a real contradiction or a clearly \
fabricated specific. When in doubt, treat the claim as supported.

Keep each issue to one short sentence. If nothing qualifies, return \
{{"supported": true, "issues": []}}.

SOURCES:
{sources}

ANSWER:
{answer}
"""


def build_verification_prompt(answer: str, sources_text: str, source_limit: int = 16000) -> str:
    """Build the critic prompt. PURE."""
    return _VERIFICATION_PROMPT.format(
        sources=sources_text[:source_limit],
        answer=answer.strip(),
    )


def parse_verification(raw: str) -> VerificationResult:
    """Parse the critic's JSON reply into a VerificationResult. PURE.

    Robust to markdown code fences and minor noise. On any parse failure returns
    an ``unknown`` status (never raises) so verification can't break the answer.
    """
    if not raw or not raw.strip():
        return VerificationResult(status="unknown")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    # Tolerate leading/trailing prose by extracting the first {...} block.
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        data = json.loads(text)
    except Exception:
        logger.warning("Verification parse failed; treating as unknown")
        return VerificationResult(status="unknown")

    supported = data.get("supported")
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    issues = [str(i).strip() for i in issues if str(i).strip()]

    if supported is True and not issues:
        return VerificationResult(status="supported", issues=[])
    if supported is False or issues:
        return VerificationResult(status="caveats", issues=issues)
    return VerificationResult(status="unknown", issues=issues)


def verify_answer(
    answer: str,
    sources_text: str,
    model_fn: Optional[Callable[[str, str], str]] = None,
    model: Optional[str] = None,
) -> VerificationResult:
    """Run the critic pass over ``answer`` given ``sources_text``.

    Thin LLM wrapper around the pure pieces. ``model_fn`` defaults to
    ``backend.pipeline.llm.generate``; ``model`` to ``settings.fast_model``.
    Returns ``unknown`` (never raises) if the answer is empty or the LLM fails,
    so a verification hiccup never blocks delivering the answer.
    """
    if not answer or not answer.strip():
        return VerificationResult(status="unknown")

    if model_fn is None:
        from backend.pipeline.llm import generate as model_fn  # noqa: PLC0415
    if model is None:
        from backend.config import settings  # noqa: PLC0415
        model = settings.fast_model

    prompt = build_verification_prompt(answer, sources_text)
    try:
        raw = model_fn(prompt, model)
    except Exception as e:  # noqa: BLE001 — verification must never break the answer
        logger.warning(f"Verification call failed: {e}")
        return VerificationResult(status="unknown")
    return parse_verification(raw)
