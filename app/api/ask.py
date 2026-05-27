"""POST /ask — grounded, cited answers over the retrieval + generation layers.

HTTP adapter only: validates input, calls ``answer_question``, returns the
structured grounded answer. (Query logging is added in Phase 5.)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.generation.answerer import answer_question
from app.generation.models import GroundedAnswer

logger = logging.getLogger(__name__)
router = APIRouter()


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    rerank: bool | None = None
    caller_roles: list[str] | None = None


class AskResponse(BaseModel):
    query: str
    answer: GroundedAnswer


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    try:
        answer = answer_question(
            req.query, k=req.k, rerank=req.rerank, caller_roles=req.caller_roles
        )
    except Exception:
        logger.exception("ask failed")
        raise HTTPException(status_code=502, detail="answer backend error") from None
    return AskResponse(query=req.query, answer=answer)
