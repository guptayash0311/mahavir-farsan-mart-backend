from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.deps import require_permission
from app.core.files import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, read_upload
from app.modules.business.models import BusinessPartner, Invoice, Purchase
from app.modules.business.service import (
    add_address,
    add_contact,
    add_invoice,
    add_proof,
    create_partner,
    create_payment,
    create_purchase,
    invoice_out,
    partner_out,
    payment_out,
    proof_bytes,
    purchase_out,
    update_partner,
)
from app.modules.identity.models import User

router = APIRouter()


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    roles: list[str] = Field(min_length=1)


class PartnerPatch(BaseModel):
    name: str | None = None
    roles: list[str] | None = None


class ContactIn(BaseModel):
    name: str
    phone: str = ""
    alternate_phone: str = ""
    email: str = ""
    designation: str = ""
    notes: str = ""


class AddressIn(BaseModel):
    line1: str
    city: str = ""
    state: str = ""
    postal_code: str = ""


class PurchaseItemIn(BaseModel):
    description: str
    amount: Decimal = Field(gt=0)


class PurchaseIn(BaseModel):
    partner_id: UUID
    purchased_on: date
    items: list[PurchaseItemIn]


class InvoiceIn(BaseModel):
    invoice_number: str
    amount: Decimal = Field(gt=0)
    due_date: date


class PaymentIn(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)
    paid_on: date
    method: str = ""
    reference: str = ""
    notes: str = ""


@router.get("/business-partners")
def partners(actor: User = Depends(require_permission("vendor.read")), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(select(BusinessPartner).where(BusinessPartner.archived_at.is_(None)).order_by(BusinessPartner.name)).all()
    return [partner_out(session, row) for row in rows]


@router.post("/business-partners", status_code=status.HTTP_201_CREATED)
def add_partner(
    body: PartnerIn,
    actor: User = Depends(require_permission("vendor.update")),
    session: Session = Depends(get_session),
) -> dict:
    return partner_out(session, create_partner(session, actor, body.name, body.roles))


@router.get("/business-partners/{partner_id}")
def partner_detail(
    partner_id: UUID,
    actor: User = Depends(require_permission("vendor.read")),
    session: Session = Depends(get_session),
) -> dict:
    partner = session.get(BusinessPartner, partner_id)
    if partner is None or partner.archived_at is not None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return partner_out(session, partner)


@router.patch("/business-partners/{partner_id}")
def patch_partner(
    partner_id: UUID,
    body: PartnerPatch,
    actor: User = Depends(require_permission("vendor.update")),
    session: Session = Depends(get_session),
) -> dict:
    return partner_out(session, update_partner(session, actor, partner_id, body.name, body.roles))


@router.get("/business-partners/{partner_id}/contacts")
def contacts(
    partner_id: UUID,
    actor: User = Depends(require_permission("vendor.read")),
    session: Session = Depends(get_session),
) -> list[dict]:
    return partner_detail(partner_id, actor, session)["contacts"]


@router.post("/business-partners/{partner_id}/contacts", status_code=status.HTTP_201_CREATED)
def post_contact(
    partner_id: UUID,
    body: ContactIn,
    actor: User = Depends(require_permission("vendor.update")),
    session: Session = Depends(get_session),
) -> dict:
    contact = add_contact(session, actor, partner_id, body.model_dump())
    return {"id": contact.id, "name": contact.name}


@router.post("/business-partners/{partner_id}/addresses", status_code=status.HTTP_201_CREATED)
def post_address(
    partner_id: UUID,
    body: AddressIn,
    actor: User = Depends(require_permission("vendor.update")),
    session: Session = Depends(get_session),
) -> dict:
    address = add_address(session, actor, partner_id, body.model_dump())
    return {"id": address.id, "line1": address.line1}


@router.get("/purchases")
def purchases(actor: User = Depends(require_permission("purchase.manage")), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(select(Purchase).where(Purchase.archived_at.is_(None)).order_by(Purchase.purchased_on.desc())).all()
    return [purchase_out(session, row) for row in rows]


@router.post("/purchases", status_code=status.HTTP_201_CREATED)
def post_purchase(
    body: PurchaseIn,
    actor: User = Depends(require_permission("purchase.manage")),
    session: Session = Depends(get_session),
) -> dict:
    purchase = create_purchase(session, actor, body.partner_id, body.purchased_on, [item.model_dump() for item in body.items])
    return purchase_out(session, purchase)


@router.post("/purchases/{purchase_id}/invoices", status_code=status.HTTP_201_CREATED)
def post_invoice(
    purchase_id: UUID,
    body: InvoiceIn,
    actor: User = Depends(require_permission("purchase.manage")),
    session: Session = Depends(get_session),
) -> dict:
    return invoice_out(session, add_invoice(session, actor, purchase_id, body.invoice_number, body.amount, body.due_date))


@router.get("/payments")
def payments(actor: User = Depends(require_permission("payment.read")), session: Session = Depends(get_session)) -> list[dict]:
    from app.modules.business.models import Payment

    rows = session.scalars(select(Payment).order_by(Payment.paid_on.desc())).all()
    return [payment_out(session, row, include_proofs=False) for row in rows]


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def post_payment(
    body: PaymentIn,
    actor: User = Depends(require_permission("payment.create")),
    session: Session = Depends(get_session),
) -> dict:
    payment = create_payment(session, actor, body.invoice_id, body.amount, body.paid_on, body.method, body.reference, body.notes)
    return payment_out(session, payment, include_proofs=False)


@router.post("/payments/{payment_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_proof(
    payment_id: UUID,
    file: UploadFile = File(...),
    actor: User = Depends(require_permission("payment.create")),
    session: Session = Depends(get_session),
) -> dict:
    data, content_type = await read_upload(file, DOCUMENT_TYPES, MAX_DOCUMENT_BYTES)
    attachment = add_proof(session, actor, payment_id, data, content_type, file.filename or "proof")
    return {"id": attachment.id, "filename": attachment.filename}


@router.get("/payments/{payment_id}/attachments/{attachment_id}")
def download_proof(
    payment_id: UUID,
    attachment_id: UUID,
    actor: User = Depends(require_permission("payment.proof.read")),
    session: Session = Depends(get_session),
) -> Response:
    data, content_type, filename = proof_bytes(session, payment_id, attachment_id)
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/invoices/{invoice_id}")
def invoice_detail(
    invoice_id: UUID,
    actor: User = Depends(require_permission("payment.read")),
    session: Session = Depends(get_session),
) -> dict:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return invoice_out(session, invoice)
