"""Provider routing in the LLM layer, including the OpenAI-compatible
"<provider>/<model>" forms used to escape Gemini's free-tier daily cap."""
import pytest

from backend.pipeline import llm


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-haiku-4-5", "anthropic"),
        ("gemini-2.5-flash", "google"),
        ("gpt-4o", "openai"),
        ("o3-mini", "openai"),
        ("cerebras/llama-3.3-70b", "openai"),
        ("groq/llama-3.3-70b-versatile", "openai"),
        ("mistral/mistral-large-latest", "openai"),
        ("ollama/qwen2.5", "openai"),
    ],
)
def test_provider_routing(model, expected):
    assert llm._provider(model) == expected


def test_provider_unknown_raises():
    with pytest.raises(ValueError):
        llm._provider("llama-3.3-70b")  # bare name, no recognizable prefix


def test_compat_strips_prefix_and_sets_base_url(monkeypatch):
    """A "<provider>/<model>" name must hit that provider's base_url with the
    bare model name and the provider's key."""
    captured = {}

    class _FakeClient:
        def __init__(self, api_key=None, base_url=None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr(llm.settings, "cerebras_api_key", "sk-test", raising=False)
    monkeypatch.setattr("openai.OpenAI", _FakeClient)

    client, real_model = llm._openai_client_and_model("cerebras/llama-3.3-70b")

    assert real_model == "llama-3.3-70b"
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://api.cerebras.ai/v1"


def test_compat_missing_key_raises_with_hint(monkeypatch):
    monkeypatch.setattr(llm.settings, "groq_api_key", "", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm._openai_client_and_model("groq/llama-3.3-70b-versatile")


def test_ollama_needs_no_key(monkeypatch):
    """Ollama is local — it must build a client without any API key set."""
    captured = {}

    class _FakeClient:
        def __init__(self, api_key=None, base_url=None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr("openai.OpenAI", _FakeClient)
    monkeypatch.setattr(llm.settings, "ollama_base_url", "http://localhost:11434/v1", raising=False)

    client, real_model = llm._openai_client_and_model("ollama/qwen2.5")

    assert real_model == "qwen2.5"
    assert captured["base_url"] == "http://localhost:11434/v1"
