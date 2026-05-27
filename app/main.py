"""FastAPI application entry point.

Phase 0 ships only the app object and a ``/health`` endpoint that verifies
Elasticsearch and PostgreSQL connectivity. Retrieval, generation, and the
``/search`` and ``/ask`` routes arrive in later phases.
"""

from __future__ import annotations

from fastapi import FastAPI, Response
from pydantic import BaseModel

from app.api.ask import router as ask_router
from app.api.search import router as search_router
from app.config import settings

app = FastAPI(
    title="grounded-rag-assistant",
    version="0.1.0",
    description="Grounded RAG assistant over Elasticsearch and AI-search docs.",
)

app.include_router(search_router)
app.include_router(ask_router)


class DependencyHealth(BaseModel):
    ok: bool
    detail: str


class HealthResponse(BaseModel):
    status: str  # "ok" when every dependency is healthy, otherwise "degraded"
    elasticsearch: DependencyHealth
    postgres: DependencyHealth


def _check_elasticsearch() -> DependencyHealth:
    """Ping Elasticsearch; never raise."""
    try:
        from elasticsearch import Elasticsearch

        client = Elasticsearch(settings.es_url, request_timeout=2)
        try:
            if client.ping():
                return DependencyHealth(ok=True, detail="reachable")
            return DependencyHealth(ok=False, detail="ping returned false")
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 - health must report, not crash
        return DependencyHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")


def _check_postgres() -> DependencyHealth:
    """Open a short-lived connection and run SELECT 1; never raise."""
    try:
        import psycopg

        with psycopg.connect(settings.postgres_dsn, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return DependencyHealth(ok=True, detail="reachable")
    except Exception as exc:  # noqa: BLE001 - health must report, not crash
        return DependencyHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")


@app.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    """Liveness + dependency readiness.

    Returns 200 only when both Elasticsearch and PostgreSQL are reachable;
    otherwise 503 so orchestrators and the compose healthcheck can gate on it.
    """
    es = _check_elasticsearch()
    pg = _check_postgres()
    healthy = es.ok and pg.ok
    response.status_code = 200 if healthy else 503
    return HealthResponse(
        status="ok" if healthy else "degraded",
        elasticsearch=es,
        postgres=pg,
    )
