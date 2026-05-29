"""POST /ask — grounded, cited answer endpoint.

Thin HTTP adapter over :func:`app.generation.answerer.answer_question`. All
retrieval and generation logic lives in the core packages; this layer only
validates input and adapts the result to HTTP.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_embedder, get_es_client, get_provider, get_reranker
from app.config import get_settings
from app.generation.answerer import answer_question
from app.generation.models import GroundedAnswer
from app.generation.providers.base import LLMProvider

logger = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=10, ge=1, le=100)
    rerank: bool | None = None
    caller_roles: list[str] | None = None


@router.post("/ask", response_model=GroundedAnswer)
def ask(
    request: AskRequest,
    provider: LLMProvider = Depends(get_provider),
) -> GroundedAnswer:
    settings = get_settings()
    rerank = settings.rerank_enabled if request.rerank is None else request.rerank

    try:
        return answer_question(
            request.query,
            client=get_es_client(),
            embedder=get_embedder(),
            provider=provider,
            index=settings.elasticsearch_index,
            k=request.k,
            caller_roles=request.caller_roles,
            rerank=rerank,
            reranker=get_reranker() if rerank else None,
            rank_constant=settings.rrf_rank_constant,
            rank_window=settings.rrf_rank_window,
            rerank_candidate_pool=settings.rerank_candidate_pool,
        )
    except Exception:
        logger.exception("Answer generation failed for query=%r", request.query)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="answer backend unavailable",
        ) from None
