"""Fallback LLM provider.

Wraps a primary provider and a fallback provider. When the primary fails because
its tokens/quota are not available (e.g. Gemini free-tier 429 / RESOURCE_EXHAUSTED),
the call is retried against the fallback (typically local Ollama) instead of
surfacing the error. Other errors propagate unchanged so real bugs are not masked.

Stays free of FastAPI coupling — plain provider composition.
"""

import logging

from app.generation.providers.base import GenerationResult, LLMProvider, Message
from app.generation.providers.gemini import _is_rate_limit

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        *,
        should_fallback=_is_rate_limit,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._should_fallback = should_fallback

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        json_output: bool = True,
        **opts: object,
    ) -> str:
        return self.generate_with_usage(
            messages, temperature=temperature, json_output=json_output, **opts
        ).text

    def generate_with_usage(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        json_output: bool = True,
        **opts: object,
    ) -> GenerationResult:
        try:
            return self.primary.generate_with_usage(
                messages, temperature=temperature, json_output=json_output, **opts
            )
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            logger.warning(
                "Primary provider %s unavailable (%s); falling back to %s.",
                type(self.primary).__name__,
                type(exc).__name__,
                type(self.fallback).__name__,
            )
            return self.fallback.generate_with_usage(
                messages, temperature=temperature, json_output=json_output, **opts
            )
