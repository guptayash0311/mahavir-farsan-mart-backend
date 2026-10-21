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


