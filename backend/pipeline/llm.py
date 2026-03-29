"""
Provider-agnostic LLM layer. Routes to the right SDK based on model name prefix:
  claude-*   → Anthropic
  gemini-*   → Google
  gpt-* / o* → OpenAI

Usage:
  generate("some prompt", model=settings.fast_model)          # non-streaming
  stream_generate("some prompt", model=settings.synthesis_model)  # streaming generator

All three providers are optional at import time — a missing API key only raises
an error if you actually try to call that provider.
"""
import logging
from typing import Generator

from backend.config import settings

logger = logging.getLogger(__name__)


def _provider(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "google"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ValueError(
        f"Cannot determine provider for model '{model}'. "
        "Expected prefix: claude-, gemini-, gpt-, o1/o3/o4."
    )


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
    from openai import OpenAI
    key = settings.openai_api_key
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY required for model '{model}'")
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
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
    from openai import OpenAI
    key = settings.openai_api_key
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY required for model '{model}'")
    logger.info(f"Synthesizing with OpenAI: {model}")
    client = OpenAI(api_key=key)
    with client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        stream=True,
    ) as stream:
        for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text
