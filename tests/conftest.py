import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.core.database import get_engine
from app.core.rate_limit import clear_rate_limits
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    clear_rate_limits()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db(client: TestClient) -> None:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL is not reachable")
    if "users" not in inspect(get_engine()).get_table_names():
        pytest.skip("Application tables are not migrated")
    return None
