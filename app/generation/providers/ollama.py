"""Ollama provider (local HTTP, fully offline).

Talks to a local Ollama server's ``/api/chat``. Reads ``OLLAMA_HOST`` and
``OLLAMA_MODEL`` from settings.
"""

from __future__ import annotations

from app.config import settings
from app.generation.providers.base import LLMProvider, Message


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ollama_model

    def generate(self, messages: list[Message], **opts) -> str:
        import httpx

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": opts.get("temperature", 0.0)},
        }
        if opts.get("json"):
            payload["format"] = "json"
        resp = httpx.post(f"{self.host}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
