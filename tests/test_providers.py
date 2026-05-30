"""Unit tests for the LLM provider factory (no network calls)."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation.providers import GeminiProvider, OllamaProvider, build_provider


def test_factory_selects_gemini() -> None:
    settings = Settings(llm_provider="gemini", gemini_api_key="dummy-key")
    provider = build_provider(settings)
    assert isinstance(provider, GeminiProvider)


def test_factory_selects_ollama() -> None:
    settings = Settings(llm_provider="ollama")
    provider = build_provider(settings)
    assert isinstance(provider, OllamaProvider)


def test_factory_rejects_unknown_provider() -> None:
    settings = Settings(llm_provider="openai")
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_provider(settings)


def test_gemini_requires_api_key() -> None:
    settings = Settings(llm_provider="gemini", gemini_api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_provider(settings)


def test_gemini_default_model_is_2_5_flash() -> None:
    """2.0-flash was retired 2026-03-03; the default must be 2.5-flash."""
    settings = Settings(llm_provider="gemini", gemini_api_key="dummy-key")
    provider = build_provider(settings)
    assert provider.model == "gemini-2.5-flash"


class _RateLimitError(Exception):
    code = 429


class _FakeModels:
    """Fakes google-genai's client.models, failing with 429 a fixed number of times."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def generate_content(self, *, model: str, contents: str, config: object) -> object:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _RateLimitError("429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(text='{"answered": false}', usage_metadata=None)


def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.generation.providers.gemini.time.sleep", lambda _s: None)


def test_gemini_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    provider = GeminiProvider("dummy-key", max_retries=2, backoff_base_s=0.0)
    models = _FakeModels(fail_times=2)
    provider.client = SimpleNamespace(models=models)

    result = provider.generate_with_usage([{"role": "user", "content": "hi"}])

    assert models.calls == 3  # 1 initial + 2 retries
    assert result.text == '{"answered": false}'


def test_gemini_reraises_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sleep(monkeypatch)
    provider = GeminiProvider("dummy-key", max_retries=2, backoff_base_s=0.0)
    models = _FakeModels(fail_times=99)
    provider.client = SimpleNamespace(models=models)

    with pytest.raises(_RateLimitError):
        provider.generate_with_usage([{"role": "user", "content": "hi"}])
    assert models.calls == 3  # gives up after max_retries, does not loop forever


def test_generate_with_usage_default_delegates_to_generate() -> None:
    """A provider that only implements generate() still works via the base
    generate_with_usage(), reporting zero usage. This is the back-compat
    contract every test fake relies on."""
    from app.generation.providers.base import LLMProvider

    class TextOnlyProvider(LLMProvider):
        def generate(self, messages, *, temperature=0.0, json_output=True, **opts):
            return "hello"

    result = TextOnlyProvider().generate_with_usage([{"role": "user", "content": "x"}])
    assert result.text == "hello"
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.model == ""
