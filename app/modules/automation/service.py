from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import shop_today, utc_now
from app.modules.automation.models import Notification, Reminder, ReminderRule, ScheduledJob
from app.modules.automation.rules import document_expiry, is_suppressed, payment_due, payment_overdue
from app.modules.business.balance import outstanding
from app.modules.business.models import Invoice, Payment
from app.modules.documents.models import Document


def _balance(session: Session, invoice: Invoice):
    payments = session.scalars(select(Payment.amount).where(Payment.invoice_id == invoice.id)).all()
    return outstanding(invoice.amount, list(payments))


def _matches(session: Session, rule: ReminderRule, today) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    if rule.condition_type in {"payment_due", "payment_overdue"}:
        for invoice in session.scalars(select(Invoice)).all():
            balance = _balance(session, invoice)
            if rule.condition_type == "payment_due" and payment_due(invoice.due_date, today, rule.lead_time_hours, balance):
                found.append(("invoice", invoice.id))
            if rule.condition_type == "payment_overdue" and payment_overdue(invoice.due_date, today, balance):
                found.append(("invoice", invoice.id))
    if rule.condition_type == "document_expiry":
        for document in session.scalars(select(Document).where(Document.archived_at.is_(None))).all():
            if document_expiry(document.expiry_date, today, rule.lead_time_hours):
                found.append(("document", document.id))
    return found


def run_cycle(session: Session, now: datetime | None = None) -> int:
    moment = now or utc_now()
    today = shop_today()
    created = 0
    rules = session.scalars(select(ReminderRule).where(ReminderRule.enabled.is_(True))).all()
    for rule in rules:
        for entity_type, entity_id in _matches(session, rule, today):
            last = session.scalar(
                select(Reminder)
                .where(Reminder.rule_id == rule.id, Reminder.entity_id == entity_id)
                .order_by(Reminder.generated_at.desc())
            )
            if last is not None and is_suppressed(last.generated_at, moment, rule.suppression_window_hours):
                continue
            reminder = Reminder(
                rule_id=rule.id,
                entity_type=entity_type,
                entity_id=entity_id,
                status="open",
                generated_at=moment,
            )
            session.add(reminder)
            session.flush()
            session.add(Notification(reminder_id=reminder.id, channel="admin_list", status="sent", created_at=moment))
            created += 1
    job = session.scalar(select(ScheduledJob).where(ScheduledJob.name == "reminders"))
    if job is None:
        job = ScheduledJob(name="reminders", status="ok", last_run_at=moment)
        session.add(job)
    else:
        job.status = "ok"
        job.last_run_at = moment
    session.commit()
    return created


def ensure_default_rules(session: Session) -> None:
    defaults = [
        ("Payment due", "payment_due", 72, 24),
        ("Payment overdue", "payment_overdue", 0, 24),
        ("Document expiry", "document_expiry", 168, 24),
    ]
    for name, condition, lead, window in defaults:
        exists = session.scalar(select(ReminderRule).where(ReminderRule.condition_type == condition, ReminderRule.name == name))
        if exists is None:
            session.add(
                ReminderRule(
                    name=name,
                    condition_type=condition,
                    lead_time_hours=lead,
                    suppression_window_hours=window,
                    enabled=True,
                )
            )
    session.flush()
