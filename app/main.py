from typing import Any

import psycopg
from elasticsearch import Elasticsearch
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name)

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
