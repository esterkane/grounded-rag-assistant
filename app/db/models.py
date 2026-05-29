"""Row models for the application database (query_log, feedback).

Plain Pydantic models, no FastAPI coupling. The API layer returns these directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackRow(BaseModel):
    id: int
    query_log_id: int
    rating: str
    correction_text: str | None = None
    reviewer: str | None = None
    created_at: datetime


class QueryLogSummary(BaseModel):
    """A query_log row without the (potentially large) payload — for list views."""

    id: int
    query: str
    answered: bool
    flagged: bool
    latency_ms: int | None = None
    provider: str = ""
    retrieval_mode: str = ""
    created_at: datetime


class QueryLogDetail(QueryLogSummary):
    """A single query_log row with its answer text, full payload, and feedback."""

    answer: str = ""
    payload: dict = Field(default_factory=dict)
    feedback: list[FeedbackRow] = Field(default_factory=list)
