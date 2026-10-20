from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import shop_today, utc_now
from app.core.database import get_session
from app.core.deps import require_permission
from app.core.money import money_str
from app.core.pagination import Page, pagination_params
from app.modules.business.balance import outstanding
from app.modules.business.models import BusinessPartner, Invoice, PartnerRole, Payment
from app.modules.catalog.models import Product
from app.modules.cms.models import Campaign
from app.modules.cms.schedule import campaign_is_active
from app.modules.commerce.models import Inquiry
from app.modules.documents.models import Document
from app.modules.governance.models import SystemSetting
from app.modules.identity.models import AuditLog, User

router = APIRouter()


class SettingIn(BaseModel):
    value: object


def _outstanding_total(session: Session) -> Decimal:
    total = Decimal("0.00")
    for invoice in session.scalars(select(Invoice)).all():
        payments = session.scalars(select(Payment.amount).where(Payment.invoice_id == invoice.id)).all()
        balance = outstanding(invoice.amount, list(payments))
        if balance > 0:
            total += balance
    return total


@router.get("/audit-logs")
def audit_logs(
    params=Depends(pagination_params),
    actor: User = Depends(require_permission("audit.read")),
    session: Session = Depends(get_session),
) -> Page[dict]:
    rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc())).all()
    start = (params.page - 1) * params.page_size
    page = rows[start : start + params.page_size]
    return Page(
        items=[
            {
                "id": row.id,
                "actor_id": row.actor_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "before": row.before_json,
                "after": row.after_json,
                "created_at": row.created_at,
            }
            for row in page
        ],
        page=params.page,
        page_size=params.page_size,
        total=len(rows),
    )


@router.get("/admin/dashboard")
def dashboard(actor: User = Depends(require_permission("user.read")), session: Session = Depends(get_session)) -> dict:
    today = shop_today()
    now = utc_now()
    open_inquiries = session.scalar(select(func.count()).select_from(Inquiry).where(Inquiry.status.in_(["new", "reviewing"]))) or 0
    active_campaigns = 0
    for campaign in session.scalars(select(Campaign).where(Campaign.archived_at.is_(None))).all():
        if campaign_is_active(campaign.status, campaign.start_at, campaign.end_at, now, campaign.archived_at):
            active_campaigns += 1
    expiring = 0
    for document in session.scalars(select(Document).where(Document.archived_at.is_(None), Document.expiry_date.is_not(None))).all():
        if document.expiry_date is not None and today <= document.expiry_date <= today.fromordinal(today.toordinal() + 30):
            expiring += 1
    published_products = session.scalar(
        select(func.count()).select_from(Product).where(Product.status == "published", Product.archived_at.is_(None))
    ) or 0
    vendors = session.scalar(
        select(func.count())
        .select_from(PartnerRole)
        .join(BusinessPartner, BusinessPartner.id == PartnerRole.partner_id)
        .where(PartnerRole.role == "vendor", BusinessPartner.archived_at.is_(None))
    ) or 0
    return {
        "open_inquiries": open_inquiries,
        "active_campaigns": active_campaigns,
        "outstanding_total": money_str(_outstanding_total(session)),
        "documents_expiring": expiring,
        "published_products": published_products,
        "vendors": vendors,
    }


@router.get("/settings")
def settings(actor: User = Depends(require_permission("settings.read")), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return [{"key": row.key, "value": row.value_json} for row in rows]


@router.patch("/settings/{key}")
def update_setting(
    key: str,
    body: SettingIn,
    actor: User = Depends(require_permission("settings.update")),
    session: Session = Depends(get_session),
) -> dict:
    if not key.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid setting key")
    row = session.get(SystemSetting, key)
    before = None if row is None else row.value_json
    value = body.value if isinstance(body.value, dict) else {"value": body.value}
    if row is None:
        row = SystemSetting(key=key, value_json=value)
        session.add(row)
    else:
        row.value_json = value
    record_audit(session, actor.id, "settings.update", "system_setting", None, before={"key": key, "value": before}, after={"key": key, "value": value})
    session.commit()
    return {"key": key, "value": row.value_json}
