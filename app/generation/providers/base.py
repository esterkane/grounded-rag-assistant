"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.generation.models import TokenUsage

# A chat message: {"role": "system" | "user" | "assistant", "content": str}.
Message = dict[str, str]


@dataclass
class GenerationResult:
    """A generation plus the token usage and model that produced it."""

    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""


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

    def generate_with_usage(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        json_output: bool = True,
        **opts: object,
    ) -> GenerationResult:
        """Generate and report token usage.

        The default delegates to :meth:`generate` and reports empty usage, so
        providers (and test fakes) that only implement ``generate`` keep working.
        Concrete providers override this to surface real token counts.
        """
        text = self.generate(
            messages, temperature=temperature, json_output=json_output, **opts
        )
        return GenerationResult(text=text, usage=TokenUsage(), model="")
