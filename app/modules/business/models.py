import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import ArchiveMixin, TimestampMixin, UUIDPrimaryKey


class BusinessPartner(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "business_partners"

    name: Mapped[str] = mapped_column(String(200), nullable=False)


class PartnerRole(Base):
    __tablename__ = "partner_roles"
    __table_args__ = (UniqueConstraint("partner_id", "role"),)

    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_partners.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(64), primary_key=True)


class Contact(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "contacts"

    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_partners.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    alternate_phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    designation: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Address(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "addresses"

    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_partners.id"), nullable=False, index=True)
    line1: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), default="", nullable=False)


class Purchase(UUIDPrimaryKey, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "purchases"

    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_partners.id"), nullable=False, index=True)
    purchased_on: Mapped[date] = mapped_column(Date, nullable=False)


class PurchaseItem(UUIDPrimaryKey, Base):
    __tablename__ = "purchase_items"

    purchase_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchases.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class Invoice(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "invoices"

    purchase_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchases.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)


class Payment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class PaymentAttachment(UUIDPrimaryKey, Base):
    __tablename__ = "payment_attachments"

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="proof", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
