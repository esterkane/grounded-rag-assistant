"""Provider factory: select the LLM provider via the ``LLM_PROVIDER`` setting."""

from __future__ import annotations

from app.config import settings
from app.generation.providers.base import LLMProvider
from app.generation.providers.gemini import GeminiProvider
from app.generation.providers.ollama import OllamaProvider

_PROVIDERS = {"gemini": GeminiProvider, "ollama": OllamaProvider}


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or settings.llm_provider or "gemini").lower()
    try:
        return _PROVIDERS[key]()
    except KeyError:
        raise ValueError(
            f"unknown LLM_PROVIDER {key!r}; expected one of {sorted(_PROVIDERS)}"
        ) from None
