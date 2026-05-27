"""LLMProvider interface.

A minimal, provider-agnostic contract so the answerer never depends on a specific
SDK. ``generate`` takes chat-style messages and returns the model's raw text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, messages: list[Message], **opts) -> str:
        """Generate a completion. Supported opts: temperature: float, json: bool.

        ``json=True`` asks the provider to constrain output to JSON when it can.
        """
        raise NotImplementedError
