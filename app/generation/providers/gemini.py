"""Gemini provider (google-genai, free tier).

Reads ``GEMINI_API_KEY`` and ``GEMINI_MODEL`` from settings. The client is created
lazily so importing this module (and selecting providers) never requires a key.
"""

from __future__ import annotations

from app.config import settings
from app.generation.providers.base import LLMProvider, Message


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(self, messages: list[Message], **opts) -> str:
        from google.genai import types

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=opts.get("temperature", 0.0),
            response_mime_type="application/json" if opts.get("json") else None,
        )
        resp = self.client.models.generate_content(
            model=self.model, contents=contents, config=config
        )
        return resp.text or ""
