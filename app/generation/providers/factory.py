"""Provider factory — selects the LLM provider from configuration."""

from app.config import Settings
from app.generation.providers.base import LLMProvider
from app.generation.providers.gemini import GeminiProvider
from app.generation.providers.ollama import OllamaProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the configured :class:`LLMProvider` (``gemini`` or ``ollama``)."""
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    raise ValueError(
        f"Unsupported LLM_PROVIDER {settings.llm_provider!r}; expected 'gemini' or 'ollama'."
    )
