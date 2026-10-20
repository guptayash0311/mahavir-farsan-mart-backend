from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import utc_now
from app.core.database import get_session
from app.core.deps import require_permission
from app.core.pagination import Page, pagination_params
from app.modules.automation.models import Reminder, ReminderRule
from app.modules.automation.service import run_cycle
from app.modules.identity.models import User

router = APIRouter()


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    condition_type: str
    lead_time_hours: int = Field(ge=0)
    suppression_window_hours: int = Field(ge=0)
    enabled: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    lead_time_hours: int | None = Field(default=None, ge=0)
    suppression_window_hours: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


def _rule_out(rule: ReminderRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "condition_type": rule.condition_type,
        "lead_time_hours": rule.lead_time_hours,
        "suppression_window_hours": rule.suppression_window_hours,
        "enabled": rule.enabled,
    }


@router.get("/reminder-rules")
def rules(actor: User = Depends(require_permission("reminder.manage")), session: Session = Depends(get_session)) -> list[dict]:
    return [_rule_out(row) for row in session.scalars(select(ReminderRule).order_by(ReminderRule.name)).all()]


@router.post("/reminder-rules", status_code=201)
def add_rule(
    body: RuleIn,
    actor: User = Depends(require_permission("reminder.manage")),
    session: Session = Depends(get_session),
) -> dict:
    if body.condition_type not in {"payment_due", "payment_overdue", "document_expiry"}:
        raise HTTPException(status_code=400, detail="Unknown reminder condition")
    rule = ReminderRule(**body.model_dump())
    session.add(rule)
    session.flush()
    record_audit(session, actor.id, "reminder_rule.create", "reminder_rule", rule.id, after={"name": rule.name})
    session.commit()
    session.refresh(rule)
    return _rule_out(rule)


@router.patch("/reminder-rules/{rule_id}")
def patch_rule(
    rule_id: UUID,
    body: RulePatch,
    actor: User = Depends(require_permission("reminder.manage")),
    session: Session = Depends(get_session),
) -> dict:
    rule = session.get(ReminderRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    for field in ("name", "lead_time_hours", "suppression_window_hours", "enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(rule, field, value)
    record_audit(session, actor.id, "reminder_rule.update", "reminder_rule", rule.id, after={"enabled": rule.enabled})
    session.commit()
    session.refresh(rule)
    return _rule_out(rule)


@router.post("/reminders/run")
def run_reminders(actor: User = Depends(require_permission("reminder.manage")), session: Session = Depends(get_session)) -> dict:
    return {"created": run_cycle(session)}


@router.get("/reminders")
def reminders(
    params=Depends(pagination_params),
    actor: User = Depends(require_permission("reminder.manage")),
    session: Session = Depends(get_session),
) -> Page[dict]:
    rows = session.scalars(select(Reminder).order_by(Reminder.generated_at.desc())).all()
    start = (params.page - 1) * params.page_size
    page = rows[start : start + params.page_size]
    return Page(
        items=[
            {
                "id": row.id,
                "rule_id": row.rule_id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "status": row.status,
                "generated_at": row.generated_at,
                "acknowledged_at": row.acknowledged_at,
            }
            for row in page
        ],
        page=params.page,
        page_size=params.page_size,
        total=len(rows),
    )


@router.post("/reminders/{reminder_id}/acknowledge")
def acknowledge(
    reminder_id: UUID,
    actor: User = Depends(require_permission("reminder.manage")),
    session: Session = Depends(get_session),
) -> dict:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    reminder.status = "acknowledged"
    reminder.acknowledged_at = utc_now()
    record_audit(session, actor.id, "reminder.acknowledge", "reminder", reminder.id)
    session.commit()
    return {"id": reminder.id, "status": reminder.status}
