"""History-aware query reformulation (condense-question).

Turns a follow-up like "what about margins?" into a standalone query
("What were Apple's gross margins in 2023?") using the conversation history, so
the downstream vector search embeds a self-contained question instead of a
pronoun-laden fragment.

Design: the prompt builder (``build_condense_prompt``) and the skip heuristic
(``should_reformulate``) are PURE and unit-tested without any network/LLM call.
``condense_query`` is a thin wrapper that calls the existing LLM helper
(``backend.pipeline.llm.generate``); the model function is injectable so the
wrapper is testable with a fake.
"""
import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# A message that already names a concrete ticker is treated as self-contained.
_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")

# Above this word count we assume the user wrote a complete question and skip the
# (cost-bearing) reformulation call.
_SELF_CONTAINED_WORD_COUNT = 12

_CONDENSE_PROMPT = """\
Given the conversation history below and a follow-up message, rewrite the \
follow-up as a single standalone question that can be understood without the \
history. Resolve pronouns and implicit references (e.g. "it", "that company", \
"what about ...") using the history. Preserve the user's intent and any tickers, \
years, or document types. Return ONLY the rewritten standalone question, with no \
preamble or explanation.

CONVERSATION HISTORY:
{history}

FOLLOW-UP MESSAGE: {message}

STANDALONE QUESTION:"""


def _format_history(history: list, max_turns: int = 6, max_chars: int = 600) -> str:
    """Render recent, well-formed turns as 'User:'/'Assistant:' lines.

    Pure helper. Drops malformed/empty entries, keeps only the last ``max_turns``
    and truncates each turn's content to ``max_chars``.
    """
    lines: list[str] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content[:max_chars]}")
    if max_turns:
        lines = lines[-max_turns:]
    return "\n".join(lines)


def should_reformulate(history: list, message: str) -> bool:
    """Decide whether condensing is worth an LLM call. PURE.

    Skip when:
      * there is no usable history (nothing to resolve against), or
      * the message is empty/whitespace, or
      * the message already names a concrete ticker (self-contained), or
      * the message is long enough to look like a complete question.
    """
    msg = (message or "").strip()
    if not msg:
        return False
    if not _format_history(history):
        return False
    if _TICKER_RE.search(msg):
        return False
    if len(msg.split()) >= _SELF_CONTAINED_WORD_COUNT:
        return False
    return True


def build_condense_prompt(history: list, message: str) -> str:
    """Build the reformulation prompt from history + latest message. PURE."""
    return _CONDENSE_PROMPT.format(
        history=_format_history(history),
        message=(message or "").strip(),
    )


def condense_query(
    history: list,
    message: str,
    model: Optional[str] = None,
    model_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Return a standalone query for ``message``.

    Thin LLM wrapper around the pure pieces above. Returns the original message
    unchanged when the heuristic says reformulation is unnecessary, when the LLM
    call fails, or when the LLM returns an empty result — so retrieval always
    has a usable query and is never broken by a bad/absent API key.

    ``model_fn`` is injectable for testing; it defaults to
    ``backend.pipeline.llm.generate``. ``model`` defaults to ``settings.fast_model``.
    """
    original = (message or "").strip()
    if not should_reformulate(history, message):
        return original

    if model_fn is None:
        from backend.pipeline.llm import generate as model_fn  # noqa: PLC0415
    if model is None:
        from backend.config import settings  # noqa: PLC0415
        model = settings.fast_model

    prompt = build_condense_prompt(history, message)
    try:
        result = model_fn(prompt, model)
    except Exception as e:  # noqa: BLE001 — never let reformulation break retrieval
        logger.warning(f"Query reformulation failed, using original message: {e}")
        return original

    rewritten = (result or "").strip()
    if not rewritten:
        return original
    logger.info(f"Reformulated query: {original!r} -> {rewritten!r}")
    return rewritten
