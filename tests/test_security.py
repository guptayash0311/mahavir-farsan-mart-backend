import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import clear_rate_limits


def test_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_product_search_responds_quickly(client: TestClient, db) -> None:
    started = time.perf_counter()
    response = client.get("/api/v1/products?q=snack")
    assert response.status_code == 200
    assert time.perf_counter() - started < 2


def test_login_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    clear_rate_limits()
    try:
        for _ in range(2):
            client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "password123"})
        blocked = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "password123"})
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
    finally:
        get_settings.cache_clear()
        clear_rate_limits()
