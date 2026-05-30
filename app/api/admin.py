"""Admin JSON API for the review workflow.

Read access to ``query_log`` and write access to ``feedback``. These are thin
HTTP adapters over :mod:`app.db.repository`; they contain no business logic of
their own. Database errors are not leaked to clients.
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.db.connection import connect
from app.db.models import FeedbackRow, QueryLogDetail, QueryLogSummary
from app.db.repository import get_query_log, insert_feedback, list_query_logs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_RATINGS = {"up", "down"}


class FeedbackRequest(BaseModel):
    rating: str = Field(description="'up' or 'down'")
    correction_text: str | None = None
    reviewer: str | None = None


@router.get("/logs", response_model=list[QueryLogSummary])
def list_logs(
    flagged: bool = False,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[QueryLogSummary]:
    """List query logs, newest-first. ``flagged=true`` returns only the queue."""
    try:
        with connect() as conn:
            return list_query_logs(
                conn, flagged_only=flagged, start=start, end=end, limit=limit
            )
    except Exception:
        logger.exception("Failed to list query logs")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None


@router.get("/logs/{log_id}", response_model=QueryLogDetail)
def get_log(log_id: int) -> QueryLogDetail:
    """Fetch one query log with its retrieved chunks (payload) and feedback."""
    detail = _load_log(log_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="query log not found"
        )
    return detail


@router.post(
    "/logs/{log_id}/feedback",
    response_model=FeedbackRow,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(log_id: int, body: FeedbackRequest) -> FeedbackRow:
    """Record up/down feedback (with optional correction) on a query log."""
    rating = body.rating.strip().lower()
    if rating not in _VALID_RATINGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rating must be 'up' or 'down'",
        )
    try:
        with connect() as conn:
            if get_query_log(conn, log_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="query log not found",
                )
            insert_feedback(
                conn,
                query_log_id=log_id,
                rating=rating,
                correction_text=body.correction_text,
                reviewer=body.reviewer,
            )
            conn.commit()
            rows = get_query_log(conn, log_id).feedback
        return rows[0]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to submit feedback for log %d", log_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None


def _load_log(log_id: int) -> QueryLogDetail | None:
    try:
        with connect() as conn:
            return get_query_log(conn, log_id)
    except Exception:
        logger.exception("Failed to load query log %d", log_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None
