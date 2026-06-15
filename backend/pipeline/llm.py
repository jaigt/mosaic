"""
Provider-agnostic LLM layer. Routes to the right SDK based on model name prefix:
  claude-*          → Anthropic
  gemini-*          → Google
  gpt-* / o*        → OpenAI
  <provider>/<model> → an OpenAI-compatible endpoint (base_url swap), where
                       <provider> is one of: cerebras, groq, mistral, ollama.
                       e.g. "cerebras/llama-3.3-70b", "ollama/qwen2.5".

The "<provider>/" forms exist to escape Gemini's stingy free-tier daily cap:
Cerebras (~1M tok/day), Groq (~1k req/day), and Mistral (~1B tok/month) all have
no-credit-card free tiers, and Ollama runs fully local with no key and no limit.

Usage:
  generate("some prompt", model=settings.fast_model)          # non-streaming
  stream_generate("some prompt", model=settings.synthesis_model)  # streaming generator

All providers are optional at import time — a missing API key only raises an
error if you actually try to call that provider.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Generator, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


# ── Transient-error retry ──────────────────────────────────────────────────────
# Free/low-cost providers (notably Cerebras) intermittently return 429
# "queue_exceeded" / "high traffic" or 503/529 under load — these are transient,
# not hard quota errors, and succeed on a quick retry. Hard quota errors (e.g.
# Gemini's daily cap) and auth errors are NOT retried; they re-raise immediately.

_TRANSIENT_SUBSTRINGS = (
    "queue_exceeded", "too_many_requests", "high traffic",
    "overloaded", "try again", "temporarily unavailable",
)


def _is_transient(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (429, 503, 529):
        # 429 can also mean a hard daily quota — only retry the "transient" flavor.
        if code == 429:
            return any(s in str(exc).lower() for s in _TRANSIENT_SUBSTRINGS)
        return True
    return any(s in str(exc).lower() for s in _TRANSIENT_SUBSTRINGS)


def _with_retry(call, *, attempts: int = 5, base_delay: float = 1.5):
    """Run ``call()``, retrying transient overload errors with exponential backoff.
    Used for the request-initiating call; for streaming, wrap stream creation only
    (before any token is yielded) so retries never duplicate output."""
    for i in range(attempts):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — re-raised below unless transient
            if not _is_transient(exc) or i == attempts - 1:
                raise
            delay = base_delay * (2 ** i)
            logger.warning("Transient LLM error (attempt %d/%d), retrying in %.1fs: %s",
                           i + 1, attempts, delay, str(exc)[:120])
            time.sleep(delay)


# ── Native tool / function calling ────────────────────────────────────────────
# A provider-neutral surface the ReAct agent can use when the model supports
# native function-calling (more reliable than parsing JSON out of free text).
# Only Gemini is implemented today; other providers fall back to text-ReAct.

@dataclass
class ToolSpec:
    """A tool the model may call. ``parameters`` is a minimal JSON-schema-ish
    dict: {"properties": {name: {"type": "string"|"integer", "description": ...}},
    "required": [...]}."""

    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    args: dict = field(default_factory=dict)


@dataclass
class AgentTurn:
    """One model turn: either tool calls to execute, or final text (gather done)."""

    text: Optional[str] = None
    tool_calls: list = field(default_factory=list)


def supports_native_tools(model: str) -> bool:
    """Whether ``model`` has a native function-calling path here (Gemini only)."""
    return model.startswith("gemini-")


def _to_gemini_schema(parameters: dict):
    """Build a Gemini types.Schema (OBJECT) from a minimal param dict."""
    from google.genai import types

    _TYPE = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN"}
    props = {}
    for pname, pspec in (parameters.get("properties") or {}).items():
        props[pname] = types.Schema(
            type=_TYPE.get(pspec.get("type", "string"), "STRING"),
            description=pspec.get("description", ""),
        )
    return types.Schema(type="OBJECT", properties=props, required=parameters.get("required", []))


class GeminiToolSession:
    """Stateful native function-calling session for Gemini.

    Threads the multi-turn ``contents`` list across the loop: ``start`` sends the
    user question, each ``respond`` sends back tool results, and both return an
    :class:`AgentTurn` (tool calls to run, or final text meaning "done gathering").
    """

    def __init__(self, system: str, tools: list, model: str):
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=settings.google_api_key)
        self._model = model
        decls = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters=_to_gemini_schema(t.parameters)
            )
            for t in tools
        ]
        self._config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)],
        )
        self._contents: list = []

    def _send(self) -> AgentTurn:
        resp = self._client.models.generate_content(
            model=self._model, contents=self._contents, config=self._config
        )
        cand = resp.candidates[0]
        # Record the model turn so the next request carries the full history.
        self._contents.append(cand.content)
        calls, texts = [], []
        for part in (cand.content.parts or []):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                calls.append(ToolCall(name=fc.name, args=dict(fc.args or {})))
            elif getattr(part, "text", None):
                texts.append(part.text)
        return AgentTurn(text=("".join(texts) or None), tool_calls=calls)

    def start(self, user_text: str) -> AgentTurn:
        self._contents.append(
            self._types.Content(role="user", parts=[self._types.Part(text=user_text)])
        )
        return self._send()

    def respond(self, results: list) -> AgentTurn:
        """``results`` is a list of (tool_name, result_str)."""
        parts = [
            self._types.Part.from_function_response(name=name, response={"result": result})
            for name, result in results
        ]
        self._contents.append(self._types.Content(role="user", parts=parts))
        return self._send()


# OpenAI-compatible providers reached via a base_url swap. Map the "<provider>/"
# prefix → (base_url, settings attribute holding the key, free-signup hint).
# Ollama is keyless (local), so its key attribute is None.
_OPENAI_COMPAT = {
    "cerebras": ("https://api.cerebras.ai/v1", "cerebras_api_key",
                 "free key (no card) at https://cloud.cerebras.ai"),
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key",
             "free key (no card) at https://console.groq.com/keys"),
    "mistral": ("https://api.mistral.ai/v1", "mistral_api_key",
                "free key at https://console.mistral.ai"),
    "ollama": (None, None, "run a local model: `ollama serve` (https://ollama.com)"),
}


def _provider(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "google"
    if model.split("/", 1)[0] in _OPENAI_COMPAT:
        return "openai"  # routed through the OpenAI SDK with a base_url swap
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ValueError(
        f"Cannot determine provider for model '{model}'. Expected prefix: "
        "claude-, gemini-, gpt-, o1/o3/o4, or <provider>/<model> for "
        f"{'/'.join(_OPENAI_COMPAT)}."
    )


def _openai_client_and_model(model: str):
    """Return (OpenAI client, real_model_name). For a "<provider>/<model>" name,
    swap in that provider's base_url + key; otherwise use native OpenAI."""
    from openai import OpenAI

    # max_retries=0: disable the SDK's *own* retry. It sleeps the server's
    # retry-after (Cerebras sends ~60s on a 429), which would otherwise stall
    # ingest invisibly. Our _with_retry governs retries with faster, bounded
    # backoff and a clean fall-through to the raw-text path.
    prefix = model.split("/", 1)[0]
    if prefix in _OPENAI_COMPAT:
        base_url, key_attr, hint = _OPENAI_COMPAT[prefix]
        real_model = model.split("/", 1)[1]
        if prefix == "ollama":
            return OpenAI(api_key="ollama", base_url=settings.ollama_base_url, max_retries=0), real_model
        key = getattr(settings, key_attr)
        if not key:
            raise RuntimeError(
                f"{key_attr.upper()} required for model '{model}' — {hint}"
            )
        return OpenAI(api_key=key, base_url=base_url, max_retries=0), real_model

    key = settings.openai_api_key
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY required for model '{model}'")
    return OpenAI(api_key=key, max_retries=0), model


# ── Non-streaming (for fast/cheap calls: table summarization, filter extraction) ──

def generate(prompt: str, model: str) -> str:
    provider = _provider(model)
    if provider == "anthropic":
        return _generate_anthropic(prompt, model)
    if provider == "google":
        return _generate_google(prompt, model)
    return _generate_openai(prompt, model)


def _generate_anthropic(prompt: str, model: str) -> str:
    import anthropic
    key = settings.anthropic_api_key
    if not key:
        raise RuntimeError(f"ANTHROPIC_API_KEY required for model '{model}'")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _generate_google(prompt: str, model: str) -> str:
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


def _generate_openai(prompt: str, model: str) -> str:
    client, real_model = _openai_client_and_model(model)
    response = _with_retry(lambda: client.chat.completions.create(
        model=real_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    ))
    return response.choices[0].message.content


# ── Streaming (for synthesis — the user-facing response) ──

def stream_generate(prompt: str, model: str) -> Generator[str, None, None]:
    provider = _provider(model)
    if provider == "anthropic":
        yield from _stream_anthropic(prompt, model)
    elif provider == "google":
        yield from _stream_google(prompt, model)
    else:
        yield from _stream_openai(prompt, model)


def _stream_anthropic(prompt: str, model: str) -> Generator[str, None, None]:
    import anthropic
    key = settings.anthropic_api_key
    if not key:
        raise RuntimeError(f"ANTHROPIC_API_KEY required for model '{model}'")
    logger.info(f"Synthesizing with Claude: {model}")
    client = anthropic.Anthropic(api_key=key)
    with client.messages.stream(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        yield from stream.text_stream


def _stream_google(prompt: str, model: str) -> Generator[str, None, None]:
    from google import genai
    logger.info(f"Synthesizing with Gemini: {model}")
    client = genai.Client(api_key=settings.google_api_key)
    for chunk in client.models.generate_content_stream(model=model, contents=prompt):
        if chunk.text:
            yield chunk.text


def _stream_openai(prompt: str, model: str) -> Generator[str, None, None]:
    client, real_model = _openai_client_and_model(model)
    logger.info(f"Synthesizing via OpenAI-compatible endpoint: {model}")
    # Retry only the stream-opening call: the transient 429 is raised here, before
    # any token is produced, so a retry can't duplicate already-yielded output.
    stream = _with_retry(lambda: client.chat.completions.create(
        model=real_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        stream=True,
    ))
    with stream as s:
        for chunk in s:
            text = chunk.choices[0].delta.content
            if text:
                yield text
