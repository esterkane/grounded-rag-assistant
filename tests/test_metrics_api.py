"""Integration tests for GET /metrics (requires PostgreSQL).

Seeds query_log rows via the repository and asserts the aggregate summary —
counts, token totals/averages, estimated cost, and latency p50/p95.
"""

import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.db.migrate import run_migrations
from app.db.repository import insert_query_log
from app.main import create_app


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    run_migrations()


@pytest.fixture
def clean_db() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE feedback, query_log RESTART IDENTITY CASCADE")
        conn.commit()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed(conn, *, answered, flagged, latency_ms, in_tok, out_tok, cost):
    insert_query_log(
        conn,
        query="q",
        answer="a" if answered else "",
        answered=answered,
        flagged=flagged,
        latency_ms=latency_ms,
        provider="gemini",
        retrieval_mode="hybrid",
        payload={},
        model="gemini-2.0-flash",
        input_tokens=in_tok,
        output_tokens=out_tok,
        estimated_cost_usd=cost,
    )


def test_metrics_summary_aggregates(clean_db: None, client: TestClient) -> None:
    with connect() as conn:
        _seed(conn, answered=True, flagged=False, latency_ms=100, in_tok=100, out_tok=20, cost=0.001)  # noqa: E501
        _seed(conn, answered=True, flagged=False, latency_ms=200, in_tok=200, out_tok=40, cost=0.002)  # noqa: E501
        _seed(conn, answered=False, flagged=True, latency_ms=300, in_tok=50, out_tok=0, cost=0.0)
        conn.commit()

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_queries"] == 3
    assert body["answered"] == 2
    assert body["insufficient"] == 1
    assert body["flagged"] == 1

    assert body["total_input_tokens"] == 350
    assert body["total_output_tokens"] == 60
    assert body["total_tokens"] == 410
    assert body["avg_total_tokens"] == pytest.approx(410 / 3)

    assert body["total_estimated_cost_usd"] == pytest.approx(0.003)

    # Latency percentiles over [100, 200, 300]: p50 = 200, p95 = 290.
    assert body["latency_p50_ms"] == pytest.approx(200.0)
    assert body["latency_p95_ms"] == pytest.approx(290.0)
    assert body["avg_latency_ms"] == pytest.approx(200.0)


def test_metrics_empty_is_zeroed(clean_db: None, client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_queries"] == 0
    assert body["total_tokens"] == 0
    assert body["latency_p50_ms"] == 0.0
