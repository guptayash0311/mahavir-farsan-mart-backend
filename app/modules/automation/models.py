import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import UUIDPrimaryKey


class ReminderRule(UUIDPrimaryKey, Base):
    __tablename__ = "reminder_rules"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_time_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suppression_window_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Reminder(UUIDPrimaryKey, Base):
    __tablename__ = "reminders"

    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reminder_rules.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notifications"

    reminder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reminders.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="sent", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScheduledJob(UUIDPrimaryKey, Base):
    __tablename__ = "scheduled_jobs"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
