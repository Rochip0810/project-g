from fastapi.testclient import TestClient

from project_g.infrastructure.config import AppEnvironment, Settings
from project_g.interfaces.api import create_app


def _create_test_settings() -> Settings:
    return Settings(
        app_env=AppEnvironment.TEST,
        app_name="project-g-test",
        app_version="0.1.0-test",
        log_level="WARNING",
    )


def test_application_uses_project_settings() -> None:
    app = create_app(_create_test_settings())

    assert app.title == "Project G API"
    assert app.version == "0.1.0-test"
    assert app.openapi_url == "/api/v1/openapi.json"


def test_health_endpoint_returns_liveness_response() -> None:
    app = create_app(_create_test_settings())

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "project-g-test",
        "version": "0.1.0-test",
        "environment": "test",
    }


def test_readiness_endpoint_returns_ready_response() -> None:
    app = create_app(_create_test_settings())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "application": "project-g-test",
        "version": "0.1.0-test",
        "environment": "test",
    }


def test_openapi_document_is_generated() -> None:
    app = create_app(_create_test_settings())

    with TestClient(app) as client:
        response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200

    payload = response.json()

    assert payload["info"]["title"] == "Project G API"
    assert payload["info"]["version"] == "0.1.0-test"
    assert "/api/v1/health" in payload["paths"]
    assert "/api/v1/health/readiness" in payload["paths"]


def test_unknown_endpoint_returns_not_found() -> None:
    app = create_app(_create_test_settings())

    with TestClient(app) as client:
        response = client.get("/api/v1/not-found")

    assert response.status_code == 404
