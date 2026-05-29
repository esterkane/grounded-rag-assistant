"""GET /metrics — operational summary over query_log.

Token, cost, and latency aggregates for the answers served so far. A thin HTTP
adapter over :func:`app.db.repository.metrics_summary`.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.db.connection import connect
from app.db.models import MetricsSummary
from app.db.repository import metrics_summary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsSummary)
def metrics() -> MetricsSummary:
    """Return query counts, token totals/averages, cost, and latency p50/p95."""
    try:
        with connect() as conn:
            return metrics_summary(conn)
    except Exception:
        logger.exception("Failed to compute metrics")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="metrics backend unavailable",
        ) from None
