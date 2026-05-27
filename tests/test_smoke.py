"""Phase 0 smoke tests.

Pure, no live services. Confirms the package imports and the FastAPI app exposes
a /health route. Dependency checks (ES/Postgres) are exercised by integration
tests against the running stack, not here.
"""

from app.config import settings
from app.main import app


def test_settings_load_with_defaults():
    assert settings.es_index == "rag_chunks"
    assert settings.llm_provider in {"gemini", "ollama"}
    assert settings.postgres_dsn.startswith("postgresql://")


def test_health_route_registered():
    paths = {route.path for route in app.routes}
    assert "/health" in paths
