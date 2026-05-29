"""Server-rendered review UI (FastAPI + Jinja2, no Node, no build step).

Two pages:

- ``GET /review`` — a queue of flagged/failed queries (all queries when
  ``?flagged=false``).
- ``GET /review/{id}`` — detail: the query, retrieved chunks, the generated
  answer with citations, and a feedback form posting back to
  ``POST /review/{id}/feedback``.

The pages are presentation only; all data access goes through
:mod:`app.db.repository`.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.connection import connect
from app.db.repository import get_query_log, insert_feedback, list_query_logs

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_class=HTMLResponse)
def queue(request: Request, flagged: bool = True) -> HTMLResponse:
    """Render the review queue (flagged-only by default)."""
    try:
        with connect() as conn:
            logs = list_query_logs(conn, flagged_only=flagged, limit=200)
    except Exception:
        logger.exception("Failed to load review queue")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None
    return templates.TemplateResponse(
        request, "queue.html", {"logs": logs, "flagged": flagged}
    )


@router.get("/{log_id}", response_class=HTMLResponse)
def detail(request: Request, log_id: int) -> HTMLResponse:
    """Render the detail page for one query log."""
    try:
        with connect() as conn:
            log = get_query_log(conn, log_id)
    except Exception:
        logger.exception("Failed to load query log %d", log_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="query log not found"
        )
    return templates.TemplateResponse(request, "detail.html", {"log": log})


@router.post("/{log_id}/feedback")
def submit_feedback(
    log_id: int,
    rating: str = Form(...),
    correction_text: str = Form(""),
    reviewer: str = Form(""),
) -> RedirectResponse:
    """Persist feedback from the detail-page form, then redirect back to it."""
    if rating.strip().lower() not in {"up", "down"}:
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
                rating=rating.strip().lower(),
                correction_text=correction_text,
                reviewer=reviewer,
            )
            conn.commit()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to submit feedback for log %d", log_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="review backend unavailable",
        ) from None
    # PRG: redirect so a refresh does not re-post the feedback.
    return RedirectResponse(
        url=f"/review/{log_id}", status_code=status.HTTP_303_SEE_OTHER
    )
