"""Integration tests for the Phase-5 review UI and feedback capture.

Requires PostgreSQL (the local stack, `make up`). They exercise the real
repository against a real database: feedback must persist, and the flagged queue
must isolate failed / low-confidence queries.
"""

import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.db.migrate import run_migrations
from app.db.repository import get_feedback_for_log, insert_query_log, list_query_logs
from app.main import create_app


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    run_migrations()


@pytest.fixture
def clean_db() -> None:
    """Start each test from empty query_log/feedback tables."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE feedback, query_log RESTART IDENTITY CASCADE")
        conn.commit()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _insert(conn, *, query: str, answered: bool, flagged: bool) -> int:
    return insert_query_log(
        conn,
        query=query,
        answer="" if not answered else "An answer.",
        answered=answered,
        flagged=flagged,
        latency_ms=12,
        provider="gemini",
        retrieval_mode="hybrid",
        payload={
            "query": query,
            "answered": answered,
            "sources": [
                {"chunk_id": "c1", "source_url": "http://x/doc#a", "title": "Doc A"}
            ],
            "claims": [{"text": "A claim.", "citations": ["c1"]}],
            "dropped_citations": [],
        },
    )


def test_flagged_queue_isolates_flagged_queries(clean_db: None, client: TestClient) -> None:
    with connect() as conn:
        flagged_id = _insert(conn, query="off-topic question", answered=False, flagged=True)
        ok_id = _insert(conn, query="answerable question", answered=True, flagged=False)
        conn.commit()

    # Repository layer.
    with connect() as conn:
        flagged_only = list_query_logs(conn, flagged_only=True)
    ids = {row.id for row in flagged_only}
    assert flagged_id in ids
    assert ok_id not in ids

    # Admin JSON endpoint.
    resp = client.get("/admin/logs", params={"flagged": "true"})
    assert resp.status_code == 200
    returned = {row["id"] for row in resp.json()}
    assert returned == {flagged_id}

    # Without the filter, both are returned.
    resp_all = client.get("/admin/logs", params={"flagged": "false"})
    all_ids = {row["id"] for row in resp_all.json()}
    assert {flagged_id, ok_id} <= all_ids

    # HTML queue shows only the flagged query by default.
    html = client.get("/review").text
    assert "off-topic question" in html
    assert "answerable question" not in html


def test_feedback_form_persists(clean_db: None, client: TestClient) -> None:
    with connect() as conn:
        log_id = _insert(conn, query="how does vector search work?", answered=True, flagged=False)
        conn.commit()

    resp = client.post(
        f"/review/{log_id}/feedback",
        data={"rating": "down", "correction_text": "Should cite the kNN doc.", "reviewer": "sru"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/review/{log_id}"

    with connect() as conn:
        feedback = get_feedback_for_log(conn, log_id)
    assert len(feedback) == 1
    assert feedback[0].rating == "down"
    assert feedback[0].correction_text == "Should cite the kNN doc."
    assert feedback[0].reviewer == "sru"


def test_admin_feedback_endpoint_persists(clean_db: None, client: TestClient) -> None:
    with connect() as conn:
        log_id = _insert(conn, query="another question", answered=True, flagged=False)
        conn.commit()

    resp = client.post(f"/admin/logs/{log_id}/feedback", json={"rating": "up"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["rating"] == "up"
    assert body["query_log_id"] == log_id

    with connect() as conn:
        feedback = get_feedback_for_log(conn, log_id)
    assert len(feedback) == 1


def test_admin_feedback_rejects_bad_rating(clean_db: None, client: TestClient) -> None:
    with connect() as conn:
        log_id = _insert(conn, query="q", answered=True, flagged=False)
        conn.commit()

    resp = client.post(f"/admin/logs/{log_id}/feedback", json={"rating": "sideways"})
    assert resp.status_code == 422


def test_get_missing_log_returns_404(clean_db: None, client: TestClient) -> None:
    assert client.get("/admin/logs/999999").status_code == 404
    assert client.get("/review/999999").status_code == 404
