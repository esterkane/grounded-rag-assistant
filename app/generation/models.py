"""Data models for grounded generation.

Plain Pydantic models with no FastAPI coupling so the answerer can be reused as
an MCP tool later.
"""

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """LLM token counts for one answer (summed across any retries)."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class Source(BaseModel):
    """A retrieved chunk that was actually cited in the answer."""

    chunk_id: str
    source_url: str
    title: str


class Claim(BaseModel):
    """A single claim in the answer with the chunk_ids that support it."""

    text: str
    citations: list[str] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    """Structured, citation-grounded answer.

    ``answered`` and ``insufficient`` are always opposites; ``insufficient`` is
    kept as an explicit field so callers do not have to negate ``answered``.
    """

    query: str
    answered: bool
    insufficient: bool
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    # Citations the model emitted that did not map to a retrieved chunk; dropped
    # from claims and recorded here for observability.
    dropped_citations: list[str] = Field(default_factory=list)
    # Observability (Phase 6): the model used and token counts for this answer.
    # None/"" when no LLM was invoked (e.g. no chunks retrieved).
    model: str = ""
    usage: TokenUsage | None = None
