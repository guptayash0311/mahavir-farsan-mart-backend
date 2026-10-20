from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    postgres_user: str = "mahavir"
    postgres_password: str = "mahavir"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mahavir"
    database_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    shop_timezone: str = "Asia/Kolkata"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        if self.database_url.strip():
            return self
        url = URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
        self.database_url = url.render_as_string(hide_password=False)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
