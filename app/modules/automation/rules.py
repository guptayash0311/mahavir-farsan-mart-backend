from datetime import date, datetime, timedelta
from decimal import Decimal


def within_lead(target: date, today: date, lead_time_hours: int) -> bool:
    window_days = max(lead_time_hours // 24, 0)
    return today <= target <= today + timedelta(days=window_days)


def payment_due(due: date, today: date, lead_time_hours: int, balance: Decimal) -> bool:
    return balance > 0 and within_lead(due, today, lead_time_hours)


def payment_overdue(due: date, today: date, balance: Decimal) -> bool:
    return balance > 0 and due < today


def document_expiry(expiry: date | None, today: date, lead_time_hours: int) -> bool:
    if expiry is None:
        return False
    return within_lead(expiry, today, lead_time_hours)


def is_suppressed(last_generated_at: datetime | None, now: datetime, window_hours: int) -> bool:
    if last_generated_at is None or window_hours <= 0:
        return False
    return now - last_generated_at < timedelta(hours=window_hours)
