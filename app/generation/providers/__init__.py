"""LLM provider abstraction.

A small, provider-agnostic interface (:class:`LLMProvider`) plus concrete
implementations for Gemini and Ollama, selected by a factory from the
``LLM_PROVIDER`` setting. No provider-specific code may leak into the answerer.
"""

from app.generation.providers.base import LLMProvider
from app.generation.providers.factory import build_provider
from app.generation.providers.gemini import GeminiProvider
from app.generation.providers.ollama import OllamaProvider

__all__ = ["LLMProvider", "GeminiProvider", "OllamaProvider", "build_provider"]
