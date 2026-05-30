"""Provider factory — selects the LLM provider(s) from configuration."""

import logging

from app.config import Settings
from app.generation.providers.base import LLMProvider
from app.generation.providers.fallback import FallbackProvider
from app.generation.providers.gemini import GeminiProvider
from app.generation.providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


def _build_single(name: str, settings: Settings) -> LLMProvider:
    """Construct one provider by name (``gemini`` or ``ollama``)."""
    if name == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if name == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    raise ValueError(
        f"Unsupported LLM_PROVIDER {name!r}; expected 'gemini' or 'ollama'."
    )


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the configured provider.

    With ``LLM_FALLBACK`` set to a different provider, the primary is wrapped in a
    :class:`FallbackProvider` so that primary quota/rate-limit failures degrade to
    the fallback (typically local Ollama) instead of erroring out. If the primary
    is Gemini and no API key is configured, the fallback is used directly.
    """
    primary_name = settings.llm_provider.lower()
    fallback_name = settings.llm_fallback.lower()
    # A fallback equal to the primary adds nothing; treat it as "no fallback".
    if fallback_name == primary_name:
        fallback_name = ""

    if not fallback_name:
        return _build_single(primary_name, settings)

    fallback = _build_single(fallback_name, settings)
    # Gemini "tokens not available" also covers a missing key: degrade rather than
    # crash at construction so the stack still answers via the fallback.
    if primary_name == "gemini" and not settings.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY not set; using %r provider without Gemini.",
            fallback_name,
        )
        return fallback
    primary = _build_single(primary_name, settings)
    return FallbackProvider(primary, fallback)
