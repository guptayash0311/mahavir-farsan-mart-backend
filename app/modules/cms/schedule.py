from datetime import datetime


def campaign_is_active(status: str, start_at: datetime, end_at: datetime, now: datetime, archived_at: datetime | None) -> bool:
    if archived_at is not None or status != "published":
        return False
    return start_at <= now <= end_at


def section_is_visible(enabled: bool, visible_from: datetime | None, visible_until: datetime | None, now: datetime) -> bool:
    if not enabled:
        return False
    if visible_from is not None and visible_from > now:
        return False
    if visible_until is not None and visible_until < now:
        return False
    return True
