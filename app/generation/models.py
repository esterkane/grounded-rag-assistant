"""Data models for grounded generation.

Plain Pydantic models with no FastAPI coupling so the answerer can be reused as
an MCP tool later.
"""

from pydantic import BaseModel, Field


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
