"""Ollama provider (local HTTP, fully offline)."""

import httpx

from app.generation.models import TokenUsage
from app.generation.providers.base import GenerationResult, LLMProvider, Message


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

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
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_output:
            payload["format"] = "json"

        response = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        usage = TokenUsage(
            input_tokens=body.get("prompt_eval_count", 0) or 0,
            output_tokens=body.get("eval_count", 0) or 0,
        )
        return GenerationResult(
            text=body["message"]["content"], usage=usage, model=self.model
        )
