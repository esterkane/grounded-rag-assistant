"""Data-access functions for query_log and feedback.

Pure functions over an open psycopg connection (see :mod:`app.db.connection`).
No FastAPI coupling — the API and review-UI layers call these and adapt the
results to HTTP. Callers are responsible for committing.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from app.db.models import (
    FeedbackRow,
    MetricsSummary,
    QueryLogDetail,
    QueryLogSummary,
)

_SUMMARY_COLUMNS = (
    "id, query, answered, flagged, latency_ms, provider, retrieval_mode, created_at"
)


def insert_query_log(
    conn: psycopg.Connection,
    *,
    query: str,
    answer: str,
    answered: bool,
    flagged: bool,
    latency_ms: int | None,
    provider: str,
    retrieval_mode: str,
    payload: dict,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
) -> int:
    """Insert a query_log row and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO query_log
                (query, answer, answered, flagged, latency_ms, provider,
                 retrieval_mode, payload, model, input_tokens, output_tokens,
                 total_tokens, estimated_cost_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                query,
                answer,
                answered,
                flagged,
                latency_ms,
                provider,
                retrieval_mode,
                Jsonb(payload),
                model,
                input_tokens,
                output_tokens,
                input_tokens + output_tokens,
                estimated_cost_usd,
            ),
        )
        return cur.fetchone()["id"]


def list_query_logs(
    conn: psycopg.Connection,
    *,
    flagged_only: bool = False,
    start: date | None = None,
    end: date | None = None,
    limit: int = 100,
) -> list[QueryLogSummary]:
    """List query_log rows newest-first, optionally filtered.

    ``start``/``end`` are inclusive calendar-date bounds on ``created_at``;
    ``flagged_only`` restricts to flagged (insufficient / low-confidence) rows.
    """
    clauses: list[str] = []
    params: list[object] = []
    if flagged_only:
        clauses.append("flagged = TRUE")
    if start is not None:
        clauses.append("created_at >= %s")
        params.append(start)
    if end is not None:
        # Inclusive of the end date: everything strictly before the next day.
        clauses.append("created_at < %s + INTERVAL '1 day'")
        params.append(end)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SUMMARY_COLUMNS} FROM query_log {where} "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            params,
        )
        return [QueryLogSummary.model_validate(row) for row in cur.fetchall()]


def get_query_log(conn: psycopg.Connection, log_id: int) -> QueryLogDetail | None:
    """Fetch one query_log row with its payload and feedback, or None."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_SUMMARY_COLUMNS}, answer, payload FROM query_log WHERE id = %s",
            (log_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    detail = QueryLogDetail.model_validate(row)
    detail.feedback = get_feedback_for_log(conn, log_id)
    return detail


def get_feedback_for_log(conn: psycopg.Connection, log_id: int) -> list[FeedbackRow]:
    """Return feedback rows for a query_log, newest-first."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, query_log_id, rating, correction_text, reviewer, created_at "
            "FROM feedback WHERE query_log_id = %s ORDER BY created_at DESC, id DESC",
            (log_id,),
        )
        return [FeedbackRow.model_validate(row) for row in cur.fetchall()]


def metrics_summary(conn: psycopg.Connection) -> MetricsSummary:
    """Aggregate operational metrics over all query_log rows."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)                                            AS total_queries,
                COALESCE(SUM(CASE WHEN answered THEN 1 ELSE 0 END), 0) AS answered,
                COALESCE(SUM(CASE WHEN flagged  THEN 1 ELSE 0 END), 0) AS flagged,
                COALESCE(SUM(CASE WHEN NOT answered THEN 1 ELSE 0 END), 0)
                                                                    AS insufficient,
                COALESCE(SUM(input_tokens), 0)                      AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0)                     AS total_output_tokens,
                COALESCE(SUM(total_tokens), 0)                      AS total_tokens,
                COALESCE(AVG(total_tokens), 0)                      AS avg_total_tokens,
                COALESCE(SUM(estimated_cost_usd), 0)                AS total_estimated_cost_usd,
                COALESCE(AVG(estimated_cost_usd), 0)                AS avg_estimated_cost_usd,
                COALESCE(
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms), 0
                )                                                   AS latency_p50_ms,
                COALESCE(
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0
                )                                                   AS latency_p95_ms,
                COALESCE(AVG(latency_ms), 0)                        AS avg_latency_ms
            FROM query_log
            """
        )
        row = cur.fetchone()
    return MetricsSummary.model_validate(row)


def insert_feedback(
    conn: psycopg.Connection,
    *,
    query_log_id: int,
    rating: str,
    correction_text: str | None = None,
    reviewer: str | None = None,
) -> int:
    """Insert a feedback row and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feedback (query_log_id, rating, correction_text, reviewer)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (query_log_id, rating, correction_text or None, reviewer or None),
        )
        return cur.fetchone()["id"]
