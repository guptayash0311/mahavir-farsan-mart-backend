import logging
import time

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.modules.automation.service import run_cycle

logger = logging.getLogger(__name__)


def _lock() -> bool:
    settings = get_settings()
    if not settings.redis_url:
        return True
    import redis

    client = redis.Redis.from_url(settings.redis_url)
    return bool(client.set("mahavir:reminders", "1", nx=True, ex=300))


def run_once() -> int:
    if not _lock():
        logger.info("reminder worker skipped because another run holds the lock")
        return 0
    with Session(get_engine()) as session:
        created = run_cycle(session)
    logger.info("reminder worker created %s reminders", created)
    return created


def main() -> None:
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("reminder worker failed")
        time.sleep(300)


if __name__ == "__main__":
    main()
