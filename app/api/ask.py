"""POST /ask — grounded, cited answer endpoint.

Thin HTTP adapter over :func:`app.generation.answerer.answer_question`. All
retrieval and generation logic lives in the core packages; this layer only
validates input, adapts the result to HTTP, and records the call in ``query_log``
for the Phase-5 review UI.
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_embedder, get_es_client, get_provider, get_reranker
from app.config import Settings, get_settings
from app.db.connection import connect
from app.db.repository import insert_query_log
from app.generation.answerer import answer_question
from app.generation.models import GroundedAnswer
from app.generation.providers.base import LLMProvider
from app.observability.cost import estimate_cost

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

    started = time.perf_counter()
    try:
        answer = answer_question(
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

    latency_ms = int((time.perf_counter() - started) * 1000)
    _record_query_log(settings, answer, latency_ms=latency_ms, rerank=rerank)
    return answer


def _record_query_log(
    settings: Settings, answer: GroundedAnswer, *, latency_ms: int, rerank: bool
) -> None:
    """Persist the answered call to ``query_log`` (best-effort).

    Flag insufficient or low-confidence answers (a "yes" answer that still had to
    drop citations) so the review queue can isolate them. Logging failures must
    never fail an otherwise-successful answer, so DB errors are swallowed here.
    """
    flagged = answer.insufficient or bool(answer.dropped_citations)
    retrieval_mode = "hybrid+rerank" if rerank else "hybrid"
    usage = answer.usage
    cost = estimate_cost(answer.model, usage)

    provider_name = settings.llm_provider
    if answer.model:
        if answer.model == settings.ollama_model:
            provider_name = "ollama"
        elif answer.model.startswith("gemini"):
            provider_name = "gemini"

    try:
        with connect(settings) as conn:
            insert_query_log(
                conn,
                query=answer.query,
                answer=answer.answer,
                answered=answer.answered,
                flagged=flagged,
                latency_ms=latency_ms,
                provider=provider_name,
                retrieval_mode=retrieval_mode,
                payload=answer.model_dump(),
                model=answer.model,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                estimated_cost_usd=cost,
            )
            )
            conn.commit()
    except Exception:
        logger.exception("Failed to write query_log for query=%r", answer.query)
