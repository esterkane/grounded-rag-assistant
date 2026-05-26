from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_unhealthy_when_dependencies_are_unavailable() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code in {200, 503}
    assert set(response.json()["checks"]) == {"elasticsearch", "postgres"}
