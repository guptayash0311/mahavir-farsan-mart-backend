from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.money import money_str
from app.core.slug import slugify
from app.modules.automation.rules import document_expiry, is_suppressed, payment_due, payment_overdue
from app.modules.business.balance import invoice_status, outstanding
from app.modules.cms.schedule import campaign_is_active


def test_slugify_kebab_case() -> None:
    assert slugify("Diwali Faral 2026") == "diwali-faral-2026"


def test_outstanding_is_derived() -> None:
    balance = outstanding(Decimal("100.00"), [Decimal("40.00"), Decimal("10.50")])
    assert money_str(balance) == "49.50"
    assert invoice_status(Decimal("100.00"), balance) == "partial"
    assert invoice_status(Decimal("100.00"), Decimal("0.00")) == "paid"


def test_campaign_window() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    assert campaign_is_active("published", now - timedelta(hours=1), now + timedelta(hours=1), now, None)
    assert not campaign_is_active("draft", now - timedelta(hours=1), now + timedelta(hours=1), now, None)
    assert not campaign_is_active("published", now + timedelta(days=1), now + timedelta(days=2), now, None)


def test_reminder_rules() -> None:
    today = datetime(2026, 10, 20, tzinfo=UTC).date()
    assert payment_due(today, today, 72, Decimal("10"))
    assert payment_overdue(today - timedelta(days=1), today, Decimal("10"))
    assert not payment_overdue(today, today, Decimal("10"))
    assert document_expiry(today + timedelta(days=3), today, 168)
    generated = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    assert is_suppressed(generated, generated + timedelta(hours=2), 24)
    assert not is_suppressed(generated, generated + timedelta(hours=25), 24)
