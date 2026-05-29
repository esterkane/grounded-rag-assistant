"""Unit tests for the LLM provider factory (no network calls)."""

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
