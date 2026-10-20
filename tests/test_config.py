import pytest

from app.core.config import get_settings


def test_database_url_encodes_reserved_password_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:w/rd")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "mahavir-farsan-mart-db")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == (
            "postgresql+psycopg://postgres:p%40ss%3Aw%2Frd@localhost:5432/mahavir-farsan-mart-db"
        )
    finally:
        get_settings.cache_clear()


def test_explicit_database_url_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = "postgresql+psycopg://postgres:p%40ssword@postgres:5432/mahavir"
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ssword")
    monkeypatch.setenv("DATABASE_URL", explicit)
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == explicit
    finally:
        get_settings.cache_clear()


def test_cors_origins_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")
    get_settings.cache_clear()
    try:
        assert get_settings().cors_origin_list == [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    finally:
        get_settings.cache_clear()
