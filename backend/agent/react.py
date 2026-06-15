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
from types import SimpleNamespace
from typing import Callable, Optional

from backend.pipeline.llm import ToolSpec

logger = logging.getLogger(__name__)

# Native function-calling tool declarations (used when ``native=True``). Mirror
# the text-mode tools, minus "answer": in native mode the model signals it's done
# by returning text instead of a tool call.
_TOOL_SPECS = [
    ToolSpec(
        name="search_filings",
        description="Semantic search over the SEC filing corpus. Use focused queries; set ticker when the question names a company.",
        parameters={
            "properties": {
                "query": {"type": "string", "description": "what to search for"},
                "ticker": {"type": "string", "description": "restrict to this ticker"},
                "year": {"type": "integer", "description": "restrict to this filing year"},
                "document_type": {"type": "string", "description": "10-K or 10-Q"},
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="ingest_filing",
        description="Fetch a filing from SEC EDGAR into the corpus so it can be searched. Use when the corpus lacks a company the user asked about.",
        parameters={
            "properties": {
                "ticker": {"type": "string", "description": "company ticker"},
                "document_type": {"type": "string", "description": "10-K or 10-Q"},
                "year": {"type": "integer", "description": "filing year (optional; latest if omitted)"},
            },
            "required": ["ticker"],
        },
    ),
    ToolSpec(
        name="list_corpus",
        description="List which filings the corpus currently contains.",
        parameters={"properties": {}, "required": []},
    ),
    ToolSpec(
        name="get_insider_activity",
        description="Recent insider (Form 4) buy/sell transactions for a ticker — officers/directors trading their own company's stock. Use for 'is anyone buying/selling X', insider sentiment.",
        parameters={
            "properties": {"ticker": {"type": "string", "description": "company ticker"}},
            "required": ["ticker"],
        },
    ),
    ToolSpec(
        name="get_fund_holdings",
        description="A named institution's latest 13F portfolio (top holdings). Use for 'what does <fund> hold' (e.g. Berkshire). Input is the FUND's ticker/CIK, not the stock you're researching.",
        parameters={
            "properties": {"fund": {"type": "string", "description": "the fund's ticker or CIK (e.g. BRK-B)"}},
            "required": ["fund"],
        },
    ),
    ToolSpec(
        name="funds_holding",
        description="Which tracked value-investing superinvestor funds (Buffett, Burry, Ackman, Klarman, …) hold a given stock, their position size, and whether they added/trimmed/exited last quarter. Use for 'is any smart money in <ticker>', 'who owns <ticker>'.",
        parameters={
            "properties": {"ticker": {"type": "string", "description": "the stock ticker to look up holders of"}},
            "required": ["ticker"],
        },
    ),
]

_NATIVE_SYSTEM_PROMPT = """\
You are an autonomous value-investing analyst working over a corpus of SEC
filings (10-K / 10-Q). Gather evidence by calling the provided tools — search
the corpus, ingest a missing filing from EDGAR then search it, or list what the
corpus holds. Gather from multiple companies/sections when the question compares
or spans them. The final written answer is produced separately from the evidence
you gather, so when you have enough, simply reply with a brief confirmation
(no tool call) — do NOT write the full answer yourself."""

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
- "get_insider_activity": recent insider (Form 4) buy/sell transactions for a
    ticker (officers/directors). Use for insider-sentiment questions.
    input: {"ticker": str}
- "get_fund_holdings": a named institution's latest 13F top holdings. The input
    is the FUND's ticker/CIK (e.g. BRK-B for Berkshire), not the stock you're
    researching. input: {"fund": str}
- "funds_holding": which tracked value-investing superinvestors hold a given
    stock (position size + added/trimmed/exited last quarter). Use for
    "is smart money in <ticker>" / "who owns <ticker>". input: {"ticker": str}
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
        generate_fn: Optional[Callable[[str, str], str]],
        retrieve_fn: Callable,
        ingest_fn: Callable,
        list_corpus_fn: Callable[[], str],
        model: str,
        max_steps: int = MAX_STEPS,
        native: bool = False,
        session_factory: Optional[Callable] = None,
        insider_fn: Optional[Callable] = None,
        fund_fn: Optional[Callable] = None,
        funds_holding_fn: Optional[Callable] = None,
    ):
        self._generate = generate_fn
        self._retrieve = retrieve_fn
        self._ingest = ingest_fn
        self._list_corpus = list_corpus_fn
        self._insider_fn = insider_fn
        self._fund_fn = fund_fn
        self._funds_holding_fn = funds_holding_fn
        self._model = model
        self._max_steps = max_steps
        # Native function-calling mode (more reliable than parsing JSON from
        # text). ``session_factory(system, tool_specs, model)`` builds a tool
        # session; defaults to the Gemini one but is injectable for tests.
        self._native = native
        self._session_factory = session_factory

    def run(self, message: str, history, filters: dict, on_event: Callable[[dict], None]) -> GatherResult:
        """Dispatch to the native function-calling loop or the text-ReAct loop."""
        if self._native:
            return self._run_native(message, history, filters, on_event)
        return self._run_text(message, history, filters, on_event)

    def _run_native(self, message: str, history, filters: dict, on_event: Callable[[dict], None]) -> GatherResult:
        """Evidence-gathering via native provider function-calling."""
        factory = self._session_factory
        if factory is None:
            from backend.pipeline.llm import GeminiToolSession  # noqa: PLC0415
            factory = GeminiToolSession
        system = _NATIVE_SYSTEM_PROMPT
        hist = _format_history(history)
        user_text = (f"CONVERSATION SO FAR:\n{hist}\n\n" if hist else "") + f"USER QUESTION: {message}"

        sources_by_id: dict = {}
        ready_reason = "max_steps"
        rounds = 0
        try:
            session = factory(system, _TOOL_SPECS, self._model)
            turn = session.start(user_text)
            for rounds in range(1, self._max_steps + 1):
                if not turn.tool_calls:
                    ready_reason = "answered"
                    break
                before = len(sources_by_id)
                results = []
                for tc in turn.tool_calls:
                    obs = self._execute(Action(tool=tc.name, input=tc.args or {}), filters, on_event)
                    for rc in getattr(self, "_last_retrieved", []):
                        cid = getattr(rc.chunk, "chunk_id", None)
                        if cid and cid not in sources_by_id:
                            sources_by_id[cid] = rc
                    self._last_retrieved = []
                    results.append((tc.name, obs))
                # Convergence guard: if a round of search calls surfaced no NEW
                # sources (the model is re-treading old ground), stop gathering
                # rather than burn the remaining step budget.
                searched = any(tc.name == "search_filings" for tc in turn.tool_calls)
                if searched and len(sources_by_id) == before:
                    ready_reason = "answered"
                    break
                if rounds >= self._max_steps:
                    break
                turn = session.respond(results)
        except Exception as e:  # noqa: BLE001 — answer on whatever was gathered
            logger.warning(f"Native tool loop failed: {e}")
            ready_reason = "parse_error"

        return GatherResult(
            sources=list(sources_by_id.values()),
            steps=rounds,
            transcript=[],
            ready_reason=ready_reason,
        )

    def _run_text(self, message: str, history, filters: dict, on_event: Callable[[dict], None]) -> GatherResult:
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
        if action.tool == "get_insider_activity":
            return self._do_insider(action.input, filters, on_event)
        if action.tool == "get_fund_holdings":
            return self._do_fund(action.input, on_event)
        if action.tool == "funds_holding":
            return self._do_funds_holding(action.input, filters, on_event)
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

    def _do_insider(self, inp: dict, filters: dict, on_event) -> str:
        if self._insider_fn is None:
            return "Insider data is unavailable."
        ticker = (inp.get("ticker") or filters.get("ticker") or "").strip().upper()
        if not ticker:
            return "get_insider_activity needs a ticker."
        on_event({"kind": "insiders", "label": f"Pulling {ticker} insider (Form 4) activity…"})
        try:
            activity = self._insider_fn(ticker)
        except Exception as e:  # noqa: BLE001
            return f"Insider lookup for {ticker} failed: {e}"
        text = activity.summary_text()
        # Make it a citable source so the synthesis can reference the figures.
        self._last_retrieved = [_synthetic_source(
            f"INSIDER_{ticker}", ticker, "Insider Activity (Form 4)", text, doc_type="Form 4",
        )]
        return text

    def _do_fund(self, inp: dict, on_event) -> str:
        if self._fund_fn is None:
            return "Institutional (13F) data is unavailable."
        fund = (inp.get("fund") or "").strip()
        if not fund:
            return "get_fund_holdings needs a fund ticker/CIK."
        on_event({"kind": "institutions", "label": f"Pulling {fund} 13F holdings…"})
        try:
            holdings = self._fund_fn(fund)
        except Exception as e:  # noqa: BLE001
            return f"13F lookup for {fund} failed: {e}"
        text = holdings.summary_text()
        self._last_retrieved = [_synthetic_source(
            f"FUND_{fund.upper()}", fund.upper(), "Institutional Holdings (13F)", text, doc_type="13F",
        )]
        return text

    def _do_funds_holding(self, inp: dict, filters: dict, on_event) -> str:
        if self._funds_holding_fn is None:
            return "Smart-money holdings data is unavailable."
        ticker = (inp.get("ticker") or filters.get("ticker") or "").strip().upper()
        if not ticker:
            return "funds_holding needs a ticker."
        on_event({"kind": "smart_money", "label": f"Checking which superinvestors hold {ticker}…"})
        try:
            ownership = self._funds_holding_fn(ticker)
        except Exception as e:  # noqa: BLE001
            return f"Smart-money lookup for {ticker} failed: {e}"
        text = ownership.summary_text()
        self._last_retrieved = [_synthetic_source(
            f"SMARTMONEY_{ticker}", ticker, "Superinvestor Ownership (13F)", text, doc_type="13F",
        )]
        return text


def _synthetic_source(chunk_id: str, ticker: str, section: str, text: str, doc_type: str):
    """A citable, RetrievedChunk-shaped source for non-filing tool results
    (insider/13F). Duck-types through synthesis (_format_sources) and the
    citation panel without being a real DocumentChunk (its doc_type isn't a
    filing Literal). Score 1.0 — these are exact, authoritative data."""
    chunk = SimpleNamespace(
        chunk_id=chunk_id, ticker=ticker, cik="", document_type=doc_type,
        filing_year=0, filing_quarter="—", sec_item_section=section,
        chunk_type="text", text_content=text, raw_payload=text,
    )
    return SimpleNamespace(chunk=chunk, score=1.0)


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
