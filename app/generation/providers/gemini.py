"""Gemini provider (google-genai, free-tier gemini-2.0-flash)."""

from app.generation.providers.base import LLMProvider, Message


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set; required for LLM_PROVIDER=gemini."
            )
        # Imported lazily so the module is importable without the SDK configured.
        from google import genai

        self._genai = genai
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        json_output: bool = True,
        **opts: object,
    ) -> str:
        from google.genai import types

        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = "\n\n".join(m["content"] for m in messages if m["role"] != "system")

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
            response_mime_type="application/json" if json_output else None,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        return response.text or ""
