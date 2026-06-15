"""A multi-tool ReAct evidence-gathering loop for the analyst agent.

This generalizes the round-5 fixed pipeline (one retrieval, optional one
auto-ingest) into a model-driven loop: at each step the model picks a tool —
search the corpus (with its own refined query/filters), ingest a missing filing
from EDGAR, list what the corpus holds, or declare it's ready to answer —
observing the result before deciding the next step. Once it declares ready (or
hits the step budget), the caller runs the existing streaming synthesis over the
accumulated sources and the self-verification critic pass.

Design for reliability + testability:
  * The protocol is a text ReAct loop (one JSON action per step) over the
    provider-agnostic ``generate`` — no dependency on a specific provider's
    native function-calling. The classic ReAct pattern.
  * ``parse_action`` and the prompt builders are PURE and unit-tested.
  * ``ReactAgent.run`` takes injected ``generate_fn`` / ``retrieve_fn`` /
    ``ingest_fn`` / ``list_corpus_fn`` and an ``on_event`` callback, so the whole
    loop is testable with fakes and no network.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Hard cap on tool steps so a confused model can't loop forever (and burn quota).
MAX_STEPS = 5
# How many results a single search returns into the evidence set.
_SEARCH_TOP_K = 5
# Doc types ingest_filing accepts; anything else is clamped to the annual report.
_INGESTABLE_DOC_TYPES = {"10-K", "10-Q"}

_SYSTEM_PROMPT = """\
You are an autonomous value-investing analyst working over a corpus of SEC
filings (10-K / 10-Q). You answer by GATHERING EVIDENCE with tools, then a
final answer is written separately from what you gathered — so your job in this
phase is only to collect the right source excerpts.

At each step, respond with EXACTLY ONE JSON object and nothing else:
{"thought": "<one sentence of reasoning>", "tool": "<tool>", "input": {<args>}}

Available tools:
- "search_filings": semantic search over the corpus.
    input: {"query": str, "ticker"?: str, "year"?: int, "document_type"?: "10-K"|"10-Q"}
    Use focused queries; search again with a refined query or different ticker if
    the results are thin. Prefer setting "ticker" when the question names a company.
- "ingest_filing": fetch a filing from SEC EDGAR into the corpus, THEN you can
    search it. Use this when search returns nothing for a company the user asked
    about (the corpus doesn't have it yet).
    input: {"ticker": str, "document_type"?: "10-K"|"10-Q", "year"?: int}
- "list_corpus": list which filings the corpus currently contains. input: {}
- "answer": stop gathering — you have enough evidence to answer.
    input: {}

Rules:
- Gather evidence from MULTIPLE companies/sections when the question compares or
  spans them (one search per company).
- If a search for a named company returns nothing, ingest that company's filing,
  then search again — don't give up.
- Do NOT write the final answer here; call "answer" when the evidence is enough.
"""


@dataclass
class Action:
    """A parsed model step."""

    tool: str                         # search_filings | ingest_filing | list_corpus | answer
    input: dict = field(default_factory=dict)
    thought: str = ""
    parse_ok: bool = True


def build_system_prompt(max_steps: int = MAX_STEPS) -> str:
    """PURE. (Plain concatenation — the prompt body contains literal JSON braces,
    so we must not run it through ``str.format``.)"""
    return f"{_SYSTEM_PROMPT}- You have at most {max_steps} steps. Be efficient.\n"


def _format_history(history, max_turns: int = 6, max_chars: int = 600) -> str:
    lines = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        role, content = entry.get("role"), entry.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        lines.append(f"{'User' if role == 'user' else 'Assistant'}: {content.strip()[:max_chars]}")
    return "\n".join(lines[-max_turns:])


def build_step_prompt(message: str, history, transcript: list[str]) -> str:
    """Build the per-step prompt from the question, history, and the running
    tool transcript (thoughts + observations so far). PURE."""
    hist = _format_history(history)
    parts = []
    if hist:
        parts.append(f"CONVERSATION SO FAR:\n{hist}\n")
    parts.append(f"USER QUESTION: {message}\n")
    if transcript:
        parts.append("STEPS SO FAR:\n" + "\n".join(transcript) + "\n")
    parts.append("Respond with your next action as a single JSON object.")
    return "\n".join(parts)


def parse_action(raw: str) -> Action:
    """Parse one step's JSON action. PURE.

    Robust to code fences and surrounding prose. On any parse failure returns an
    ``answer`` action with ``parse_ok=False`` so the loop ends gracefully instead
    of spinning on malformed output.
    """
    if not raw or not raw.strip():
        return Action(tool="answer", parse_ok=False)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        data = json.loads(text)
    except Exception:
        logger.warning("ReAct action parse failed; ending gather")
        return Action(tool="answer", parse_ok=False)
    tool = str(data.get("tool", "answer")).strip()
    inp = data.get("input") or {}
    if not isinstance(inp, dict):
        inp = {}
    return Action(tool=tool, input=inp, thought=str(data.get("thought", "")).strip())


def _clamp_doc_type(dt) -> Optional[str]:
    if not dt:
        return None
    dt = str(dt).upper()
    return dt if dt in _INGESTABLE_DOC_TYPES else "10-K"


@dataclass
class GatherResult:
    sources: list                      # accumulated RetrievedChunk, deduped, ranked by first-seen
    steps: int
    transcript: list[str]
    ready_reason: str                  # "answered" | "max_steps" | "parse_error"


class ReactAgent:
    """Drives the evidence-gathering loop with injected I/O functions."""

    def __init__(
        self,
        generate_fn: Callable[[str, str], str],
        retrieve_fn: Callable,
        ingest_fn: Callable,
        list_corpus_fn: Callable[[], str],
        model: str,
        max_steps: int = MAX_STEPS,
    ):
        self._generate = generate_fn
        self._retrieve = retrieve_fn
        self._ingest = ingest_fn
        self._list_corpus = list_corpus_fn
        self._model = model
        self._max_steps = max_steps

    def run(self, message: str, history, filters: dict, on_event: Callable[[dict], None]) -> GatherResult:
        """Run the loop. ``filters`` carries explicit request scoping
        (ticker/year/document_type) that seeds search/ingest when the model omits
        them. ``on_event`` is called with an agent-step dict per action."""
        system = build_system_prompt(self._max_steps)
        transcript: list[str] = []
        sources_by_id: dict = {}            # chunk_id -> RetrievedChunk (preserve first-seen order)
        last_signature: Optional[tuple] = None
        ready_reason = "max_steps"

        for step in range(1, self._max_steps + 1):
            prompt = f"{system}\n\n{build_step_prompt(message, history, transcript)}"
            try:
                raw = self._generate(prompt, self._model)
            except Exception as e:  # noqa: BLE001 — end gather gracefully, answer on what we have
                logger.warning(f"ReAct step {step} generation failed: {e}")
                ready_reason = "parse_error"
                break

            action = parse_action(raw)
            if action.tool == "answer":
                ready_reason = "answered" if action.parse_ok else "parse_error"
                if action.thought:
                    transcript.append(f"Thought: {action.thought}")
                break

            # Loop guard: identical action twice in a row → stop gathering.
            signature = (action.tool, json.dumps(action.input, sort_keys=True))
            if signature == last_signature:
                ready_reason = "answered"
                break
            last_signature = signature

            observation = self._execute(action, filters, on_event)
            thought = f"Thought: {action.thought}\n" if action.thought else ""
            transcript.append(f"{thought}Action: {action.tool} {json.dumps(action.input)}\nObservation: {observation}")
            # Merge any newly retrieved sources (dedupe by chunk_id, keep order).
            for rc in getattr(self, "_last_retrieved", []):
                cid = getattr(rc.chunk, "chunk_id", None)
                if cid and cid not in sources_by_id:
                    sources_by_id[cid] = rc
            self._last_retrieved = []

        return GatherResult(
            sources=list(sources_by_id.values()),
            steps=step,
            transcript=transcript,
            ready_reason=ready_reason,
        )

    # ── tool execution ───────────────────────────────────────────────────────
    def _execute(self, action: Action, filters: dict, on_event: Callable[[dict], None]) -> str:
        self._last_retrieved = []
        if action.tool == "search_filings":
            return self._do_search(action.input, filters, on_event)
        if action.tool == "ingest_filing":
            return self._do_ingest(action.input, filters, on_event)
        if action.tool == "list_corpus":
            on_event({"kind": "list_corpus", "label": "Checking what's in the corpus…"})
            try:
                return self._list_corpus() or "The corpus is empty."
            except Exception as e:  # noqa: BLE001
                return f"Could not list corpus: {e}"
        # Unknown tool — nudge the model to answer.
        on_event({"kind": "note", "label": f"Unknown tool '{action.tool}', wrapping up."})
        return f"Unknown tool '{action.tool}'. Call 'answer' if you have enough evidence."

    def _do_search(self, inp: dict, filters: dict, on_event) -> str:
        query = str(inp.get("query") or "").strip()
        if not query:
            return "No query provided."
        ticker = inp.get("ticker") or filters.get("ticker")
        year = inp.get("year") or filters.get("year")
        doc_type = inp.get("document_type") or filters.get("document_type")
        scope = " ".join(x for x in [ticker, str(year) if year else "", doc_type] if x).strip()
        on_event({"kind": "search", "label": f"Searching: “{query[:60]}”" + (f" [{scope}]" if scope else "")})
        try:
            chunks = self._retrieve(query=query, top_k=_SEARCH_TOP_K, ticker=ticker, year=year, document_type=doc_type)
        except Exception as e:  # noqa: BLE001
            return f"Search failed: {e}"
        self._last_retrieved = chunks
        if not chunks:
            return f"No results for '{query}'" + (f" (ticker {ticker})" if ticker else "") + "."
        return "Found:\n" + _summarize_results(chunks)

    def _do_ingest(self, inp: dict, filters: dict, on_event) -> str:
        ticker = (inp.get("ticker") or filters.get("ticker") or "").strip().upper()
        if not ticker:
            return "ingest_filing needs a ticker."
        doc_type = _clamp_doc_type(inp.get("document_type") or filters.get("document_type")) or "10-K"
        year = inp.get("year") or filters.get("year")
        span = f" ({year})" if year else " (latest)"
        on_event({"kind": "ingest", "label": f"Fetching {ticker} {doc_type}{span} from SEC EDGAR…"})
        try:
            n = self._ingest(ticker=ticker, document_type=doc_type, year=year)
            on_event({"kind": "ingest_done", "label": f"Ingested {ticker} {doc_type} ({n} chunks)."})
            return f"Ingested {ticker} {doc_type} — {n} chunks now searchable. Search it next."
        except Exception as e:  # noqa: BLE001
            on_event({"kind": "ingest_failed", "label": f"Couldn't fetch {ticker} {doc_type}: {e}"})
            return f"Ingest of {ticker} {doc_type} failed: {e}"


def _summarize_results(chunks) -> str:
    """Compact, model-facing summary of retrieved chunks. PURE given chunks."""
    lines = []
    for i, rc in enumerate(chunks, 1):
        c = rc.chunk
        snippet = (c.text_content or "").strip().replace("\n", " ")[:160]
        lines.append(
            f"  [{i}] {c.ticker} {c.document_type} {c.filing_year} ({c.filing_quarter}) "
            f"— {c.sec_item_section}: {snippet}"
        )
    return "\n".join(lines)
