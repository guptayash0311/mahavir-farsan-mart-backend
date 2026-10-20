from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app


def test_not_found_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "not_found"
    assert body["message"]
    assert body["details"] is None
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


def test_validation_error_shape() -> None:
    application = create_app()

    @application.get("/needs-int")
    def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    client = TestClient(application)
    response = client.get("/needs-int?n=abc")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert isinstance(body["details"], list)
    assert body["request_id"]


def test_unhandled_exception_hides_details() -> None:
    application: FastAPI = create_app()

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret failure")

    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "internal_error"
    assert body["message"] == "Something went wrong."
    assert body["details"] is None
    assert "secret" not in response.text
