"""Structured grounded-answer models (pydantic, not FastAPI)."""

from __future__ import annotations

from pydantic import BaseModel


class Claim(BaseModel):
    text: str
    citations: list[str]  # chunk_ids, each validated to exist in the context


class Source(BaseModel):
    chunk_id: str
    source_url: str
    title: str


class GroundedAnswer(BaseModel):
    answer: str
    claims: list[Claim]
    sources: list[Source]
    answered: bool
    insufficient: bool
