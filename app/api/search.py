"""POST /search — hybrid retrieval endpoint.

Thin HTTP adapter over the pure retrieval functions in ``app/retrieval``. It
validates input, runs hybrid retrieval, optionally reranks, and returns the
chunks with their metadata and method tags. All retrieval/ranking logic lives in
the retrieval layer, not here.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_embedder, get_es_client, get_reranker
from app.config import get_settings
from app.retrieval.models import RetrievedChunk
from app.retrieval.retriever import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=10, ge=1, le=100)
    rerank: bool | None = None
    caller_roles: list[str] | None = None


class SearchResponse(BaseModel):
    query: str
    k: int
    reranked: bool
    count: int
    results: list[RetrievedChunk]


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    settings = get_settings()
    rerank = settings.rerank_enabled if request.rerank is None else request.rerank

    # When reranking, fuse a larger candidate pool so the cross-encoder has
    # something to reorder before we trim to k.
    pool = max(request.k, settings.rerank_candidate_pool) if rerank else request.k

    try:
        fused = hybrid_search(
            get_es_client(),
            get_embedder(),
            request.query,
            pool,
            index=settings.elasticsearch_index,
            caller_roles=request.caller_roles,
            rank_constant=settings.rrf_rank_constant,
            rank_window=settings.rrf_rank_window,
        )
        if rerank:
            results = get_reranker().rerank(request.query, fused, top_k=request.k)
        else:
            results = fused[: request.k]
    except Exception:
        logger.exception("Search failed for query=%r", request.query)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search backend unavailable",
        ) from None

    return SearchResponse(
        query=request.query,
        k=request.k,
        reranked=rerank,
        count=len(results),
        results=results,
    )
