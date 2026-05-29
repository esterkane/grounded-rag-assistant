"""Data-access functions for query_log and feedback.

Pure functions over an open psycopg connection (see :mod:`app.db.connection`).
No FastAPI coupling — the API and review-UI layers call these and adapt the
results to HTTP. Callers are responsible for committing.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from app.db.models import FeedbackRow, QueryLogDetail, QueryLogSummary

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
) -> int:
    """Insert a query_log row and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO query_log
                (query, answer, answered, flagged, latency_ms, provider,
                 retrieval_mode, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
