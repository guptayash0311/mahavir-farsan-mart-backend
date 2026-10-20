from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def shop_now() -> datetime:
    from app.core.config import get_settings

    return datetime.now(ZoneInfo(get_settings().shop_timezone))


def shop_today():
    return shop_now().date()
