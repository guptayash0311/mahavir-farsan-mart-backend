from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.money import money, money_str
from app.core.storage import get_storage
from app.modules.business.balance import invoice_status, outstanding
from app.modules.business.models import (
    Address,
    BusinessPartner,
    Contact,
    Invoice,
    PartnerRole,
    Payment,
    PaymentAttachment,
    Purchase,
    PurchaseItem,
)
from app.modules.identity.models import User

PARTNER_ROLES = {"vendor", "manufacturer", "raw_material_supplier"}


def _partner(session: Session, partner_id: UUID) -> BusinessPartner:
    partner = session.get(BusinessPartner, partner_id)
    if partner is None or partner.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return partner


def _roles(session: Session, partner_id: UUID) -> list[str]:
    return list(session.scalars(select(PartnerRole.role).where(PartnerRole.partner_id == partner_id)).all())


def partner_out(session: Session, partner: BusinessPartner) -> dict:
    contacts = session.scalars(select(Contact).where(Contact.partner_id == partner.id)).all()
    addresses = session.scalars(select(Address).where(Address.partner_id == partner.id)).all()
    return {
        "id": partner.id,
        "name": partner.name,
        "roles": _roles(session, partner.id),
        "contacts": [
            {
                "id": row.id,
                "name": row.name,
                "phone": row.phone,
                "alternate_phone": row.alternate_phone,
                "email": row.email,
                "designation": row.designation,
                "notes": row.notes,
            }
            for row in contacts
        ],
        "addresses": [
            {"id": row.id, "line1": row.line1, "city": row.city, "state": row.state, "postal_code": row.postal_code}
            for row in addresses
        ],
    }


def create_partner(session: Session, actor: User, name: str, roles: list[str]) -> BusinessPartner:
    cleaned = _clean_roles(roles)
    partner = BusinessPartner(name=name.strip())
    session.add(partner)
    session.flush()
    for role in cleaned:
        session.add(PartnerRole(partner_id=partner.id, role=role))
    record_audit(session, actor.id, "partner.create", "business_partner", partner.id, after={"name": partner.name, "roles": cleaned})
    session.commit()
    session.refresh(partner)
    return partner


def update_partner(session: Session, actor: User, partner_id: UUID, name: str | None, roles: list[str] | None) -> BusinessPartner:
    partner = _partner(session, partner_id)
    if name:
        partner.name = name.strip()
    if roles is not None:
        from sqlalchemy import delete

        cleaned = _clean_roles(roles)
        session.execute(delete(PartnerRole).where(PartnerRole.partner_id == partner.id))
        for role in cleaned:
            session.add(PartnerRole(partner_id=partner.id, role=role))
    record_audit(session, actor.id, "partner.update", "business_partner", partner.id, after={"name": partner.name})
    session.commit()
    session.refresh(partner)
    return partner


def _clean_roles(roles: list[str]) -> list[str]:
    cleaned = sorted(set(roles))
    if not cleaned or any(role not in PARTNER_ROLES for role in cleaned):
        raise HTTPException(status_code=400, detail="Unknown partner role")
    return cleaned


def add_contact(session: Session, actor: User, partner_id: UUID, data: dict) -> Contact:
    _partner(session, partner_id)
    contact = Contact(partner_id=partner_id, **data)
    session.add(contact)
    record_audit(session, actor.id, "contact.create", "contact", contact.id, after={"name": contact.name})
    session.commit()
    session.refresh(contact)
    return contact


def add_address(session: Session, actor: User, partner_id: UUID, data: dict) -> Address:
    _partner(session, partner_id)
    address = Address(partner_id=partner_id, **data)
    session.add(address)
    session.commit()
    session.refresh(address)
    return address


def create_purchase(session: Session, actor: User, partner_id: UUID, purchased_on: date, items: list[dict]) -> Purchase:
    _partner(session, partner_id)
    if not items:
        raise HTTPException(status_code=400, detail="A purchase needs at least one line")
    purchase = Purchase(partner_id=partner_id, purchased_on=purchased_on)
    session.add(purchase)
    session.flush()
    for item in items:
        session.add(PurchaseItem(purchase_id=purchase.id, description=item["description"].strip(), amount=money(item["amount"])))
    record_audit(session, actor.id, "purchase.create", "purchase", purchase.id)
    session.commit()
    session.refresh(purchase)
    return purchase


def purchase_out(session: Session, purchase: Purchase) -> dict:
    items = session.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)).all()
    invoices = [invoice_out(session, row) for row in session.scalars(select(Invoice).where(Invoice.purchase_id == purchase.id)).all()]
    partner = session.get(BusinessPartner, purchase.partner_id)
    return {
        "id": purchase.id,
        "partner_id": purchase.partner_id,
        "partner_name": None if partner is None else partner.name,
        "purchased_on": purchase.purchased_on,
        "items": [{"id": row.id, "description": row.description, "amount": money_str(row.amount)} for row in items],
        "invoices": invoices,
    }


def _payments(session: Session, invoice_id: UUID) -> list[Payment]:
    return list(session.scalars(select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.paid_on)).all())


def invoice_out(session: Session, invoice: Invoice) -> dict:
    payments = _payments(session, invoice.id)
    balance = outstanding(invoice.amount, [row.amount for row in payments])
    return {
        "id": invoice.id,
        "purchase_id": invoice.purchase_id,
        "invoice_number": invoice.invoice_number,
        "amount": money_str(invoice.amount),
        "due_date": invoice.due_date,
        "status": invoice.status,
        "outstanding": money_str(balance),
        "payments": [payment_out(session, row, include_proofs=False) for row in payments],
    }


def add_invoice(session: Session, actor: User, purchase_id: UUID, invoice_number: str, amount: Decimal, due_date: date) -> Invoice:
    purchase = session.get(Purchase, purchase_id)
    if purchase is None or purchase.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if session.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number.strip())):
        raise HTTPException(status_code=409, detail="Invoice number already exists")
    invoice = Invoice(
        purchase_id=purchase.id,
        invoice_number=invoice_number.strip(),
        amount=money(amount),
        due_date=due_date,
        status="open",
    )
    session.add(invoice)
    record_audit(session, actor.id, "invoice.create", "invoice", invoice.id, after={"invoice_number": invoice.invoice_number})
    session.commit()
    session.refresh(invoice)
    return invoice


def payment_out(session: Session, payment: Payment, include_proofs: bool) -> dict:
    invoice = session.get(Invoice, payment.invoice_id)
    balance = Decimal("0")
    if invoice is not None:
        balance = outstanding(invoice.amount, [row.amount for row in _payments(session, invoice.id)])
    proofs = []
    if include_proofs:
        for row in session.scalars(select(PaymentAttachment).where(PaymentAttachment.payment_id == payment.id)).all():
            proofs.append({"id": row.id, "filename": row.filename, "url": f"/api/v1/payments/{payment.id}/attachments/{row.id}"})
    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "invoice_number": None if invoice is None else invoice.invoice_number,
        "amount": money_str(payment.amount),
        "paid_on": payment.paid_on,
        "method": payment.method,
        "reference": payment.reference,
        "notes": payment.notes,
        "outstanding": money_str(balance),
        "attachments": proofs,
    }


def create_payment(session: Session, actor: User, invoice_id: UUID, amount: Decimal, paid_on: date, method: str, reference: str, notes: str) -> Payment:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    value = money(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be positive")
    current = outstanding(invoice.amount, [row.amount for row in _payments(session, invoice.id)])
    if value > current:
        raise HTTPException(status_code=400, detail="Payment exceeds the outstanding balance")
    payment = Payment(invoice_id=invoice.id, amount=value, paid_on=paid_on, method=method.strip(), reference=reference.strip(), notes=notes.strip())
    session.add(payment)
    session.flush()
    balance = outstanding(invoice.amount, [row.amount for row in _payments(session, invoice.id)])
    invoice.status = invoice_status(invoice.amount, balance)
    record_audit(
        session,
        actor.id,
        "payment.create",
        "payment",
        payment.id,
        after={"amount": money_str(value), "outstanding": money_str(balance)},
    )
    session.commit()
    session.refresh(payment)
    return payment


def add_proof(session: Session, actor: User, payment_id: UUID, data: bytes, content_type: str, filename: str) -> PaymentAttachment:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    key = f"payments/{payment.id}/{uuid4()}"
    get_storage().put(key, data, content_type)
    attachment = PaymentAttachment(
        payment_id=payment.id,
        storage_key=key,
        content_type=content_type,
        filename=filename or "proof",
        created_at=utc_now(),
    )
    session.add(attachment)
    record_audit(session, actor.id, "payment.proof", "payment", payment.id)
    session.commit()
    session.refresh(attachment)
    return attachment


def proof_bytes(session: Session, payment_id: UUID, attachment_id: UUID) -> tuple[bytes, str, str]:
    attachment = session.get(PaymentAttachment, attachment_id)
    if attachment is None or attachment.payment_id != payment_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    return get_storage().get(attachment.storage_key), attachment.content_type, attachment.filename
