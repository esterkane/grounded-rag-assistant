"""Gemini provider (google-genai, free-tier gemini-2.5-flash).

gemini-2.0-flash was retired by Google on 2026-03-03; gemini-2.5-flash is the
current free-tier default. The model name stays configurable via GEMINI_MODEL.
"""

import logging
import time

from app.generation.models import TokenUsage
from app.generation.providers.base import GenerationResult, LLMProvider, Message

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


def _is_rate_limit(exc: Exception) -> bool:
    """True if ``exc`` looks like a Gemini 429 / RESOURCE_EXHAUSTED error."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    text = str(exc).upper()
    return "429" in text or "RESOURCE_EXHAUSTED" in text


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        max_retries: int = 2,
        backoff_base_s: float = 2.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set; required for LLM_PROVIDER=gemini."
            )
        # Imported lazily so the module is importable without the SDK configured.
        from google import genai

        self._genai = genai
        self.model = model
        # Free-tier RPM limits (~10-15 RPM) cause transient 429s; retry a few
        # times with exponential backoff before giving up.
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.client = genai.Client(api_key=api_key)

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
        from google.genai import types

        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = "\n\n".join(m["content"] for m in messages if m["role"] != "system")

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
            response_mime_type="application/json" if json_output else None,
        )
        response = self._generate_with_retry(contents, config)
        usage = TokenUsage()
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = TokenUsage(
                input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
            )
        return GenerationResult(text=response.text or "", usage=usage, model=self.model)

    def _generate_with_retry(self, contents: str, config: object) -> object:
        """Call the model, retrying on 429 with exponential backoff."""
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                if not _is_rate_limit(exc) or attempt == self.max_retries:
                    raise
                wait = self.backoff_base_s * (2**attempt)
                logger.warning(
                    "Gemini rate-limited (429); waiting %.1fs before retry %d/%d",
                    wait,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(wait)
        # Unreachable: the loop either returns or raises.
        raise RuntimeError("retry loop exited without returning")
