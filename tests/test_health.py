import pytest
from fastapi.testclient import TestClient


def test_health_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] in {"ok", "error"}
    assert body["version"] == "0.1.0"
    assert response.headers["x-request-id"]
    if body["database"] == "ok":
        assert body["status"] == "ok"
    else:
        assert body["status"] == "degraded"


def test_health_reports_database_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.health.check_database", lambda: "error")
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "database": "error",
        "version": "0.1.0",
    }


def test_health_database_ok_when_postgres_is_up(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    body = response.json()
    if body["database"] != "ok":
        pytest.skip("PostgreSQL is not reachable")
    assert body["status"] == "ok"
