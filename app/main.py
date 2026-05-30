import logging
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from elasticsearch import Elasticsearch
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.ask import router as ask_router
from app.api.metrics import router as metrics_router
from app.api.review import router as review_router
from app.api.search import router as search_router
from app.config import Settings, get_settings
from app.db.migrate import run_migrations
from app.observability import configure_logging, configure_tracing

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Tracing first so the logging trace-id filter sees a provider, then
        # structured logging, then ensure the DB schema exists.
        configure_tracing(app_settings)
        configure_logging(app_settings)
        # Best-effort: ensure the query_log/feedback tables exist so the review
        # UI works out of the box. A DB hiccup must not block the API starting.
        try:
            run_migrations(app_settings)
        except Exception:
            logger.exception("Database migration on startup failed")
        yield

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)

    app.include_router(search_router)
    app.include_router(ask_router)
    app.include_router(admin_router)
    app.include_router(review_router)
    app.include_router(metrics_router)

    @app.get("/health")
    def health() -> JSONResponse:
        checks = {
            "elasticsearch": check_elasticsearch(app_settings),
            "postgres": check_postgres(app_settings),
        }
        healthy = all(check["healthy"] for check in checks.values())
        http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=http_status,
            content={"status": "healthy" if healthy else "unhealthy", "checks": checks},
        )

    return app


def check_elasticsearch(settings: Settings) -> dict[str, Any]:
    try:
        client = Elasticsearch(settings.elasticsearch_url, request_timeout=3)
        info = client.info()
        return {
            "healthy": True,
            "cluster_name": info.get("cluster_name"),
            "version": info.get("version", {}).get("number"),
        }
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


def check_postgres(settings: Settings) -> dict[str, Any]:
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return {"healthy": True}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


app = create_app()
