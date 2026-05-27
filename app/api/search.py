"""POST /search — HTTP adapter over the pure retrieval layer.

Validates input, calls ``app.retrieval.retriever.search``, and returns results.
Contains no retrieval/ranking logic of its own and does not leak backend errors.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.retrieval.models import RetrievalResult
from app.retrieval.retriever import search as run_search

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    rerank: bool | None = None
    caller_roles: list[str] | None = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[RetrievalResult]


@router.post("/search", response_model=SearchResponse)
def search_endpoint(req: SearchRequest) -> SearchResponse:
    try:
        results = run_search(
            req.query, k=req.k, rerank=req.rerank, caller_roles=req.caller_roles
        )
    except Exception:
        logger.exception("search failed")
        raise HTTPException(status_code=502, detail="search backend error") from None
    return SearchResponse(query=req.query, count=len(results), results=results)
