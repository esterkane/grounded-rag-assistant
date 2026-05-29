"""Base LLM provider interface."""

from abc import ABC, abstractmethod

# A chat message: {"role": "system" | "user" | "assistant", "content": str}.
Message = dict[str, str]


class LLMProvider(ABC):
    """Provider-agnostic text generation interface.

    Implementations take a list of chat ``messages`` and return the model's raw
    text response. ``json_output=True`` asks the provider to constrain output to
    JSON where the backend supports it; callers must still parse defensively.
    """

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        json_output: bool = True,
        **opts: object,
    ) -> str:
        """Generate a completion for ``messages`` and return the raw text."""
