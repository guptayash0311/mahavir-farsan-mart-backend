import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine

logger = logging.getLogger(__name__)
router = APIRouter()


def check_database() -> str:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("database health check failed")
        return "error"


@router.get("/health")
def health() -> dict[str, str]:
    database = check_database()
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": get_settings().app_version,
    }
